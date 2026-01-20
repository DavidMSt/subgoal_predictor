///*
// * bilbo_position_control.cpp
// *
// *  Created on: Jan 9, 2026
// *      Author: lehmann
// */
//
//#include "bilbo_position_control.h"
//
//#include <algorithm>
//#include <cmath>
//
//// Provided by your system (global tick counter)
//extern uint32_t tick_global;
//
//// If you have send_info() in your system:
//extern void send_info(const char* fmt, ...);
//
//// ------------------------------------------------------------------------------------------------
//// Small math helpers
//// ------------------------------------------------------------------------------------------------
//
//float BILBO_PositionControl::_clampf(float v, float lo, float hi) {
//    return std::max(lo, std::min(v, hi));
//}
//
//float BILBO_PositionControl::_wrapToPi(float a) {
//    constexpr float PI = 3.14159265358979323846f;
//    while (a > PI) a -= 2.0f * PI;
//    while (a < -PI) a += 2.0f * PI;
//    return a;
//}
//
//float BILBO_PositionControl::_hypot(float x, float y) {
//    return std::sqrt(x * x + y * y);
//}
//
//float BILBO_PositionControl::_project_point_to_segment(float px, float py,
//                                                       float ax, float ay, float bx, float by,
//                                                       float& cx, float& cy) {
//    const float abx = bx - ax;
//    const float aby = by - ay;
//    const float apx = px - ax;
//    const float apy = py - ay;
//
//    const float ab2 = abx * abx + aby * aby;
//    float t = 0.0f;
//    if (ab2 > 1e-12f) {
//        t = (apx * abx + apy * aby) / ab2;
//    }
//    t = _clampf(t, 0.0f, 1.0f);
//
//    cx = ax + t * abx;
//    cy = ay + t * aby;
//    return t;
//}
//
//// ------------------------------------------------------------------------------------------------
//// Constructor / config / reset
//// ------------------------------------------------------------------------------------------------
//
//BILBO_PositionControl::BILBO_PositionControl() {
//    // safe defaults for telemetry
//    _data.current_mode = bilbo_position_control_mode_t::NONE;
//    _data.current_output = {0.0f, 0.0f};
//    _data.is_executing_command = false;
//    _data.active_command_id = 0;
//    _data.queued_waypoints = 0;
//    _data.current_segment_index = 0;
//    _data.lookahead_current = 0.0f;
//    _data.remaining_path_length = 0.0f;
//    _data.inside_final_region = false;
//}
//
//void BILBO_PositionControl::set_config(bilbo_position_control_config_t cfg) {
//    config = cfg;
//    reset();
//}
//
//bilbo_position_control_config_t BILBO_PositionControl::get_config() {
//    return config;
//}
//
//void BILBO_PositionControl::reset() {
//    abort_current_command();
//    clear_path();
//
//    _pos_i = 0.0f;
//    _ang_i = 0.0f;
//
//    _arrival_hold_time = 0.0f;
//    _inside_final = false;
//
//    _v_prev = 0.0f;
//    _w_prev = 0.0f;
//
//    _segment_index = 0;
//    _seg_t = 0.0f;
//
//    _data.current_mode = bilbo_position_control_mode_t::NONE;
//    _data.current_output = {0.0f, 0.0f};
//    _data.is_executing_command = false;
//    _data.active_command_id = 0;
//}
//
//// ------------------------------------------------------------------------------------------------
//// Path buffer
//// ------------------------------------------------------------------------------------------------
//
//void BILBO_PositionControl::clear_path() {
//    _wp_head = 0;
//    _wp_tail = 0;
//    _wp_count = 0;
//    _segment_index = 0;
//    _seg_t = 0.0f;
//}
//
//uint16_t BILBO_PositionControl::queued_waypoints() const {
//    return _wp_count;
//}
//
//bool BILBO_PositionControl::_wp_push(const bilbo_waypoint_t& wp) {
//    if (_wp_count >= WAYPOINT_BUFFER_SIZE) return false;
//    _wp_buf[_wp_tail] = wp;
//    _wp_tail = static_cast<uint16_t>((_wp_tail + 1) % WAYPOINT_BUFFER_SIZE);
//    _wp_count++;
//    return true;
//}
//
//bool BILBO_PositionControl::append_waypoint(const bilbo_waypoint_t& wp) {
//    return _wp_push(wp);
//}
//
//bool BILBO_PositionControl::append_shape(float x, float y) {
//    bilbo_waypoint_t wp;
//    wp.x = x; wp.y = y;
//    wp.type = bilbo_waypoint_type_t::SHAPE;
//    wp.gate_radius = 0.0f;
//    return _wp_push(wp);
//}
//
//bool BILBO_PositionControl::append_gate(float x, float y, float radius_m) {
//    bilbo_waypoint_t wp;
//    wp.x = x; wp.y = y;
//    wp.type = bilbo_waypoint_type_t::GATE;
//    wp.gate_radius = std::max(0.0f, radius_m);
//    return _wp_push(wp);
//}
//
//const bilbo_waypoint_t* BILBO_PositionControl::_wp_peek(uint16_t idx_from_front) const {
//    if (idx_from_front >= _wp_count) return nullptr;
//    const uint16_t idx = static_cast<uint16_t>((_wp_head + idx_from_front) % WAYPOINT_BUFFER_SIZE);
//    return &_wp_buf[idx];
//}
//
//bool BILBO_PositionControl::_wp_pop_front() {
//    if (_wp_count == 0) return false;
//    _wp_head = static_cast<uint16_t>((_wp_head + 1) % WAYPOINT_BUFFER_SIZE);
//    _wp_count--;
//    return true;
//}
//
//// ------------------------------------------------------------------------------------------------
//// Command control
//// ------------------------------------------------------------------------------------------------
//
//bool BILBO_PositionControl::start_path(uint16_t command_id, float timeout_s, float max_speed_override) {
//    if (is_executing_command()) return false;
//    if (_wp_count == 0) return false;
//
//    _active_command_id = command_id;
//    _active_timeout_s = timeout_s;
//    _active_max_speed = max_speed_override;
//
//    _command_start_tick = static_cast<uint32_t>(tick_global);
//
//    _pos_i = 0.0f;
//    _ang_i = 0.0f;
//    _arrival_hold_time = 0.0f;
//    _inside_final = false;
//
//    _segment_index = 0;
//    _seg_t = 0.0f;
//
//    current_mode = bilbo_position_control_mode_t::PATH_FOLLOW;
//    return true;
//}
//
//void BILBO_PositionControl::abort_current_command() {
//    current_mode = bilbo_position_control_mode_t::NONE;
//    _active_command_id = 0;
//    _active_timeout_s = 0.0f;
//    _active_max_speed = 0.0f;
//
//    _arrival_hold_time = 0.0f;
//    _inside_final = false;
//
//    _pos_i = 0.0f;
//    _ang_i = 0.0f;
//}
//
//bool BILBO_PositionControl::is_executing_command() const {
//    return current_mode != bilbo_position_control_mode_t::NONE;
//}
//
//// Backwards compatible single-point: clear path, push final gate waypoint, start.
//bool BILBO_PositionControl::set_position_command(position_command_t command) {
//    if (is_executing_command()) return false;
//
//    clear_path();
//
//    // Use a GATE waypoint so the robot actually goes "through" the target neighborhood.
//    const float r = (config.gate_default_radius > 0.0f) ? config.gate_default_radius
//                                                       : std::max(1e-3f, config.final_arrival_tolerance);
//
//    append_gate(command.position_ref.x_target, command.position_ref.y_target, r);
//
//    current_mode = bilbo_position_control_mode_t::POSITION_TO_POINT;
//    return start_path(command.id, command.timeout, command.max_speed);
//}
//
//// ------------------------------------------------------------------------------------------------
//// Corner speed reduction heuristic (polyline)
//// ------------------------------------------------------------------------------------------------
//
//float BILBO_PositionControl::_corner_speed_reduction(bilbo_position_state_t st,
//                                                    uint16_t seg_index,
//                                                    float dist_to_vertex) const {
//    // reduction fraction in [0..corner_speed_reduction_max]
//    const float max_red = _clampf(config.corner_speed_reduction_max, 0.0f, 1.0f);
//
//    if (config.corner_approach_dist <= 1e-6f) return 0.0f;
//    if (dist_to_vertex > config.corner_approach_dist) return 0.0f;
//
//    const bilbo_waypoint_t* A = _wp_peek(seg_index);
//    const bilbo_waypoint_t* B = _wp_peek(seg_index + 1);
//    const bilbo_waypoint_t* C = _wp_peek(seg_index + 2);
//    if (!A || !B || !C) return 0.0f;
//
//    const float v1x = B->x - A->x;
//    const float v1y = B->y - A->y;
//    const float v2x = C->x - B->x;
//    const float v2y = C->y - B->y;
//
//    const float n1 = std::sqrt(v1x*v1x + v1y*v1y);
//    const float n2 = std::sqrt(v2x*v2x + v2y*v2y);
//    if (n1 < 1e-6f || n2 < 1e-6f) return 0.0f;
//
//    const float d = _clampf((v1x*v2x + v1y*v2y) / (n1*n2), -1.0f, 1.0f);
//    const float turn_angle = std::acos(d); // 0..pi
//
//    // Normalize severity 0 (straight) -> 1 (180deg)
//    const float severity = _clampf(turn_angle / 3.14159265358979323846f, 0.0f, 1.0f);
//
//    // Also ramp in based on distance to vertex
//    const float ramp = 1.0f - _clampf(dist_to_vertex / config.corner_approach_dist, 0.0f, 1.0f);
//
//    return max_red * severity * ramp;
//}
//
//// ------------------------------------------------------------------------------------------------
//// Carrot computation along polyline
//// ------------------------------------------------------------------------------------------------
//
//bool BILBO_PositionControl::_compute_carrot(bilbo_position_state_t st,
//                                           float L,
//                                           float& carrot_x, float& carrot_y,
//                                           float& remaining_path_len,
//                                           uint16_t& seg_index_out,
//                                           float& seg_t_out) {
//    remaining_path_len = 0.0f;
//
//    // Need at least 1 waypoint to go somewhere. With 1 waypoint, segment start is current pose.
//    const bilbo_waypoint_t* W0 = _wp_peek(0);
//    if (!W0) return false;
//
//    // Build "virtual polyline": P0 = current position, then all waypoints.
//    // We'll interpret segment_index as:
//    //  seg 0: from current pose -> waypoint[0]
//    //  seg 1: waypoint[0] -> waypoint[1], etc.
//    //
//    // However, for gating / advancement we still use waypoint semantics at vertices (waypoint[i]).
//    // We'll store segment_index in this virtual space.
//    const uint16_t virtual_points = static_cast<uint16_t>(_wp_count + 1);
//    const uint16_t virtual_segments = static_cast<uint16_t>((virtual_points >= 2) ? (virtual_points - 1) : 0);
//    if (virtual_segments == 0) return false;
//
//    // clamp current segment index
//    if (_segment_index >= virtual_segments) {
//        _segment_index = static_cast<uint16_t>(virtual_segments - 1);
//        _seg_t = 1.0f;
//    }
//
//    auto get_point = [&](uint16_t vidx, float& x, float& y) {
//        if (vidx == 0) { x = st.x; y = st.y; return; }
//        const bilbo_waypoint_t* wp = _wp_peek(static_cast<uint16_t>(vidx - 1));
//        x = wp ? wp->x : st.x;
//        y = wp ? wp->y : st.y;
//    };
//
//    // Reproject onto current segment (helps recover if drifted)
//    {
//        float ax, ay, bx, by, cx, cy;
//        get_point(_segment_index, ax, ay);
//        get_point(static_cast<uint16_t>(_segment_index + 1), bx, by);
//
//        const float t_proj = _project_point_to_segment(st.x, st.y, ax, ay, bx, by, cx, cy);
//
//        // small hysteresis to prevent segment "un-advancing" when near vertex
//        const float t_new = std::max(_seg_t - (config.advance_hysteresis / std::max(_hypot(bx-ax, by-ay), 1e-6f)), t_proj);
//        _seg_t = _clampf(t_new, 0.0f, 1.0f);
//    }
//
//    // Now march forward along segments by distance L to find carrot
//    float remaining = std::max(0.0f, L);
//
//    uint16_t seg = _segment_index;
//    float t = _seg_t;
//
//    while (true) {
//        float ax, ay, bx, by;
//        get_point(seg, ax, ay);
//        get_point(static_cast<uint16_t>(seg + 1), bx, by);
//
//        const float seg_len = _hypot(bx - ax, by - ay);
//        const float seg_rem = std::max(0.0f, (1.0f - t)) * seg_len;
//
//        if (remaining <= seg_rem + 1e-9f) {
//            // Carrot lies on this segment
//            const float dt = (seg_len > 1e-9f) ? (remaining / seg_len) : 0.0f;
//            const float t_car = _clampf(t + dt, 0.0f, 1.0f);
//            carrot_x = ax + (bx - ax) * t_car;
//            carrot_y = ay + (by - ay) * t_car;
//
//            seg_index_out = seg;
//            seg_t_out = t_car;
//            break;
//        }
//
//        // move to next segment
//        remaining -= seg_rem;
//        if (seg + 1 >= virtual_segments) {
//            // end of path: carrot = final point
//            carrot_x = bx;
//            carrot_y = by;
//            seg_index_out = seg;
//            seg_t_out = 1.0f;
//            break;
//        }
//        seg = static_cast<uint16_t>(seg + 1);
//        t = 0.0f;
//    }
//
//    // Compute remaining path length from current progress to end (for braking)
//    {
//        float sum = 0.0f;
//
//        // current segment remainder
//        float ax, ay, bx, by;
//        get_point(_segment_index, ax, ay);
//        get_point(static_cast<uint16_t>(_segment_index + 1), bx, by);
//        const float seg_len = _hypot(bx - ax, by - ay);
//        sum += std::max(0.0f, (1.0f - _seg_t)) * seg_len;
//
//        // subsequent full segments
//        for (uint16_t s = static_cast<uint16_t>(_segment_index + 1); s < virtual_segments; s++) {
//            float p0x, p0y, p1x, p1y;
//            get_point(s, p0x, p0y);
//            get_point(static_cast<uint16_t>(s + 1), p1x, p1y);
//            sum += _hypot(p1x - p0x, p1y - p0y);
//        }
//
//        remaining_path_len = sum;
//    }
//
//    return true;
//}
//
//// ------------------------------------------------------------------------------------------------
//// Main update
//// ------------------------------------------------------------------------------------------------
//
//bilbo_position_control_output_t BILBO_PositionControl::update(bilbo_position_state_t st) {
//    bilbo_position_control_output_t out{0.0f, 0.0f};
//
//    if (current_mode == bilbo_position_control_mode_t::NONE) {
//        _pos_i = 0.0f;
//        _ang_i = 0.0f;
//        _arrival_hold_time = 0.0f;
//        _inside_final = false;
//        _v_prev = 0.0f;
//        _w_prev = 0.0f;
//
//        _data.current_mode = current_mode;
//        _data.current_output = out;
//        _data.is_executing_command = false;
//        _data.active_command_id = 0;
//        _data.queued_waypoints = _wp_count;
//        _data.current_segment_index = _segment_index;
//        _data.lookahead_current = 0.0f;
//        _data.remaining_path_length = 0.0f;
//        _data.inside_final_region = false;
//
//        return out;
//    }
//
//    // timeout handling
//    if (is_executing_command() && _active_timeout_s > 0.0f) {
//        const uint32_t elapsed_ticks = static_cast<uint32_t>(tick_global - _command_start_tick);
//        const float elapsed_s = static_cast<float>(elapsed_ticks) * config.Ts;
//        if (elapsed_s >= _active_timeout_s) {
//            _on_timeout();
//            out = {0.0f, 0.0f};
//            _data.current_mode = current_mode;
//            _data.current_output = out;
//            _data.is_executing_command = is_executing_command();
//            return out;
//        }
//    }
//
//    // run follower
//    if (current_mode == bilbo_position_control_mode_t::PATH_FOLLOW ||
//        current_mode == bilbo_position_control_mode_t::POSITION_TO_POINT) {
//        out = _follow_path_tick(st);
//    } else {
//        out = {0.0f, 0.0f};
//        current_mode = bilbo_position_control_mode_t::NONE;
//    }
//
//    _data.current_mode = current_mode;
//    _data.current_output = out;
//    _data.is_executing_command = is_executing_command();
//    _data.active_command_id = _active_command_id;
//    _data.queued_waypoints = _wp_count;
//    _data.current_segment_index = _segment_index;
//    _data.inside_final_region = _inside_final;
//
//    return out;
//}
//
//bilbo_position_control_data_t BILBO_PositionControl::get_data() const {
//    return _data;
//}
//
//// ------------------------------------------------------------------------------------------------
//// Path follower core
//// ------------------------------------------------------------------------------------------------
//
//bilbo_position_control_output_t BILBO_PositionControl::_follow_path_tick(bilbo_position_state_t st) {
//    bilbo_position_control_output_t out{0.0f, 0.0f};
//
//    const float Ts = config.Ts;
//
//    // No waypoints -> finish immediately
//    if (_wp_count == 0) {
//        _on_command_finished();
//        return out;
//    }
//
//    // Determine speed limit
//    float v_max = ( _active_max_speed > 0.0f ) ? _active_max_speed : config.max_speed_forward;
//    v_max = std::max(0.0f, v_max);
//
//    const float w_max = std::max(0.0f, config.max_speed_turn);
//
//    // Variable lookahead
//    float L = config.lookahead_min + config.lookahead_gain * std::fabs(_v_prev);
//    L = _clampf(L, config.lookahead_min, config.lookahead_max);
//    L = std::max(L, 1e-4f);
//
//    float carrot_x = 0.0f, carrot_y = 0.0f;
//    float remaining_len = 0.0f;
//    uint16_t carrot_seg = 0;
//    float carrot_t = 0.0f;
//
//    if (!_compute_carrot(st, L, carrot_x, carrot_y, remaining_len, carrot_seg, carrot_t)) {
//        // fail-safe
//        out = {0.0f, 0.0f};
//        _on_timeout();
//        return out;
//    }
//
//    _data.lookahead_current = L;
//    _data.remaining_path_length = remaining_len;
//
//    // Heading to carrot
//    const float dx = carrot_x - st.x;
//    const float dy = carrot_y - st.y;
//    const float dist_to_carrot = _hypot(dx, dy);
//
//    float psi_carrot = std::atan2(dy, dx);
//    float e_psi_to_carrot = _wrapToPi(psi_carrot - st.psi);
//
//    // Optional reverse mode (kept from your original, but default allow_reverse=0 is recommended)
//    bool reverse_mode = false;
//    if (config.allow_reverse) {
//        // use heading to *final* point (or carrot) to decide reverse
//        if (std::fabs(e_psi_to_carrot) > config.backwards_switch_angle) {
//            reverse_mode = true;
//        }
//    }
//    if (reverse_mode) {
//        psi_carrot = _wrapToPi(psi_carrot + 3.14159265358979323846f);
//        e_psi_to_carrot = _wrapToPi(psi_carrot - st.psi);
//    }
//
//    // ---------------- Linear PI on distance to carrot (bounded) ----------------
//    // This yields smooth buildup but is still "self-paced" by limits below.
//    float v_pi_unsat = config.kp_linear * dist_to_carrot + _pos_i;
//    float v_pi_sat = (v_max > 0.0f) ? _clampf(v_pi_unsat, -v_max, v_max) : 0.0f;
//
//    // anti-windup
//    {
//        const bool sat = (std::fabs(v_pi_unsat - v_pi_sat) > 1e-6f);
//        const float err = dist_to_carrot; // >=0
//        const bool would_push = sat && (v_pi_unsat > v_pi_sat) && (err > 0.0f);
//        if (!would_push) {
//            _pos_i += config.ki_linear * err * Ts;
//        }
//    }
//
//    float v_cmd = v_pi_sat;
//
//    // Heading-based scaling (your idea, but allow a floor via heading_cos_min)
//    float cos_scale = std::cos(e_psi_to_carrot);
//    // keep it non-negative to avoid unintentional reversal
//    cos_scale = std::max(config.heading_cos_min, std::max(0.0f, cos_scale));
//    v_cmd *= cos_scale;
//
//    if (reverse_mode) {
//        v_cmd = -v_cmd;
//    }
//
//    // ---------------- Angular PI on heading error ----------------
//    float w_pi_unsat = config.kp_angular * e_psi_to_carrot + _ang_i;
//    float w_pi_sat = (w_max > 0.0f) ? _clampf(w_pi_unsat, -w_max, w_max) : 0.0f;
//
//    // anti-windup
//    {
//        const bool sat = (std::fabs(w_pi_unsat - w_pi_sat) > 1e-6f);
//        const float err = e_psi_to_carrot;
//        const bool would_push = sat &&
//                ((w_pi_unsat > w_pi_sat && err > 0.0f) || (w_pi_unsat < w_pi_sat && err < 0.0f));
//        if (!would_push) {
//            _ang_i += config.ki_angular * err * Ts;
//        }
//    }
//
//    float w_cmd = w_pi_sat;
//
//    // ---------------- Speed limiting by yaw-rate demand (pure pursuit curvature) ----------------
//    // curvature estimate for pure pursuit:
//    //   kappa = 2*sin(e_psi)/L
//    // yaw-rate requirement roughly: w ~= v * kappa
//    const float kappa = (2.0f * std::sin(e_psi_to_carrot)) / std::max(L, 1e-4f);
//    const float kappa_abs = std::fabs(kappa);
//
//    float v_limit_yaw = v_max;
//    if (kappa_abs > config.kappa_epsilon && w_max > 0.0f) {
//        v_limit_yaw = w_max / kappa_abs;
//        v_limit_yaw = std::max(config.min_speed_yaw_limit, v_limit_yaw);
//        v_limit_yaw = std::min(v_limit_yaw, v_max);
//    }
//
//    // ---------------- Corner slowdown heuristic (polyline) ----------------
//    // "dist_to_vertex" in the virtual polyline: distance from robot to end of current segment
//    float dist_to_vertex = 0.0f;
//    {
//        // virtual segment end is waypoint[segment_index] when segment_index==0? careful:
//        // virtual segment 0 ends at waypoint[0]
//        // We'll approximate using carrot segment state: if current segment index is 0, vertex is wp[0].
//        uint16_t vidx_end = static_cast<uint16_t>(_segment_index + 1); // virtual point index
//        if (vidx_end >= 1 && (vidx_end - 1) < _wp_count) {
//            const bilbo_waypoint_t* wp_end = _wp_peek(static_cast<uint16_t>(vidx_end - 1));
//            if (wp_end) {
//                dist_to_vertex = _hypot(wp_end->x - st.x, wp_end->y - st.y);
//            }
//        }
//    }
//
//    const float red_frac = _corner_speed_reduction(st, static_cast<uint16_t>((_segment_index == 0) ? 0 : (_segment_index - 1)), dist_to_vertex);
//    const float v_limit_corner = v_max * (1.0f - red_frac);
//
//    // ---------------- End-of-path braking (distance-based) ----------------
//    // remaining_len computed from current progress to end
//    float v_limit_end = v_max;
//    if (config.end_decel > 1e-6f) {
//        // v^2 <= 2*a*d
//        v_limit_end = std::sqrt(std::max(0.0f, 2.0f * config.end_decel * remaining_len));
//        v_limit_end = std::min(v_limit_end, v_max);
//    }
//
//    // Combine all v limits
//    float v_limit = std::min(v_max, std::min(v_limit_yaw, std::min(v_limit_corner, v_limit_end)));
//    v_cmd = _clampf(v_cmd, -v_limit, v_limit);
//
//    // ---------------- Rate limiting (very important for inverted pendulum) ----------------
//    if (config.max_accel > 1e-6f) {
//        const float dv_max = config.max_accel * Ts;
//        v_cmd = _clampf(v_cmd, _v_prev - dv_max, _v_prev + dv_max);
//    }
//    if (config.max_yaw_accel > 1e-6f) {
//        const float dw_max = config.max_yaw_accel * Ts;
//        w_cmd = _clampf(w_cmd, _w_prev - dw_max, _w_prev + dw_max);
//    }
//
//    _v_prev = v_cmd;
//    _w_prev = w_cmd;
//
//    out.v_cmd = v_cmd;
//    out.psi_dot_cmd = w_cmd;
//
//    // ------------------------------------------------------------------------------------------------
//    // Waypoint advancement & final completion
//    // ------------------------------------------------------------------------------------------------
//    // Waypoint index mapping:
//    //  - virtual segment 0 ends at waypoint[0]
//    //  - virtual segment 1 ends at waypoint[1], etc.
//    // So when _segment_index advances past 0, we've "passed" waypoint[0], etc.
//    //
//    // Gate semantics: if next waypoint is GATE, require distance <= gate_radius before advancing segment.
//    // Shape semantics: advance when projection progress reaches end of segment.
//    //
//    // We update _segment_index / _seg_t implicitly via _compute_carrot() which reprojects, but we still need
//    // explicit advancement to drop waypoints from the front when they are consumed.
//    //
//    // Simplification used here:
//    //  - If we are on virtual segment 0 (current pose->wp0), gate/shape applies to wp0.
//    //  - When allowed to advance, we pop_front() and stay on segment 0 again (new wp0 becomes target),
//    //    because "current pose" re-anchors the virtual polyline each tick.
//    //
//    // This makes the ring buffer logic simple and robust.
//    //
//    // Determine if wp0 is "reached" based on its type.
//    const bilbo_waypoint_t* wp0 = _wp_peek(0);
//    const float d_wp0 = wp0 ? _hypot(wp0->x - st.x, wp0->y - st.y) : 1e9f;
//
//    bool can_pop_wp0 = false;
//    if (wp0) {
//        if (wp0->type == bilbo_waypoint_type_t::GATE) {
//            const float r = std::max(1e-6f, wp0->gate_radius);
//            if (d_wp0 <= r) can_pop_wp0 = true;
//        } else { // SHAPE
//            // For SHAPE, allow popping when we are "close enough" to the vertex OR when we've clearly passed it.
//            // Since we re-anchor segment 0 each tick, "passed" is hard to define robustly; we use a proximity threshold.
//            // Using gate_default_radius here gives a consistent "vertex snapping" behavior for shape points too.
//            const float r = std::max(1e-6f, config.gate_default_radius);
//            if (d_wp0 <= r) can_pop_wp0 = true;
//        }
//    }
//
//    // Pop intermediate waypoints, but never pop the final waypoint until completion condition satisfied.
//    if (_wp_count >= 2 && can_pop_wp0) {
//        (void)_wp_pop_front();
//        _arrival_hold_time = 0.0f;
//        _inside_final = false;
//    }
//
//    // Final completion logic (only when buffer has exactly 1 waypoint left)
//    if (_wp_count == 1) {
//        const bilbo_waypoint_t* final_wp = _wp_peek(0);
//        const float d_final = final_wp ? _hypot(final_wp->x - st.x, final_wp->y - st.y) : 1e9f;
//
//        const bool inside = (d_final <= config.final_arrival_tolerance);
//        _inside_final = inside;
//
//        if (inside) {
//            _arrival_hold_time += Ts;
//        } else {
//            _arrival_hold_time = 0.0f;
//        }
//
//        if (inside && _arrival_hold_time >= config.arrival_time) {
//            // Done: clear buffer and finish
//            clear_path();
//            _on_command_finished();
//            out = {0.0f, 0.0f};
//        }
//    } else {
//        _inside_final = false;
//    }
//
//    return out;
//}
//
//// ------------------------------------------------------------------------------------------------
//// Finished / timeout callbacks
//// ------------------------------------------------------------------------------------------------
//
//void BILBO_PositionControl::_on_command_finished() {
//    if (_active_command_id != 0) {
//        send_info("Path command %u finished", _active_command_id);
//        callbacks.element_finished.call(_active_command_id);
//    }
//
//    abort_current_command();
//}
//
//void BILBO_PositionControl::_on_timeout() {
//    if (_active_command_id != 0) {
//        send_info("Path command %u timed out!", _active_command_id);
//        callbacks.element_timeout.call(_active_command_id);
//    }
//
//    abort_current_command();
//}
