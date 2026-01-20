///*
// * bilbo_position_control_new.h
// *
// *  Created on: Jan 20, 2026
// *      Author: lehmann
// */
//
///*
// * bilbo_position_control.h
// *
// *  Created on: Jan 9, 2026
// *      Author: lehmann
// *
// *  Path follower upgrade (Jan 2026):
// *   - Waypoint ring buffer + continuous path following
// *   - Variable lookahead
// *   - Yaw-rate demand speed limiting
// *   - Shape & Gate waypoint semantics
// *   - End-of-path braking without time parameterization
// *   - Backwards compatible single-point command
// */
//
//#ifndef CONTROL_BILBO_POSITION_CONTROL_H_
//#define CONTROL_BILBO_POSITION_CONTROL_H_
//
//#include <cstdint>
//#include "twipr_estimation.h"
//
//// --------------------------------------------------------------------------------------
//// Waypoints
//// --------------------------------------------------------------------------------------
//
//enum class bilbo_waypoint_type_t : uint8_t {
//    SHAPE = 0,  // geometry point (may be corner-cut)
//    GATE  = 1,  // must enter gate_radius around waypoint before advancing
//};
//
//struct bilbo_waypoint_t {
//    float x;
//    float y;
//    bilbo_waypoint_type_t type;
//    float gate_radius; // [m] used if type==GATE (ignored otherwise)
//};
//
//// --------------------------------------------------------------------------------------
//// Backwards compatible single-point command
//// --------------------------------------------------------------------------------------
//
//struct position_reference_t {
//    float x_target;
//    float y_target;
//};
//
//struct position_command_t {
//    uint16_t id;
//    position_reference_t position_ref;
//    float max_speed; // if <=0 uses config.max_speed_forward
//    float timeout;   // if >0 abort after timeout seconds
//};
//
//// --------------------------------------------------------------------------------------
//// Controller output
//// --------------------------------------------------------------------------------------
//
//struct bilbo_position_control_output_t {
//    float v_cmd;       // [m/s]
//    float psi_dot_cmd; // [rad/s]
//};
//
//// --------------------------------------------------------------------------------------
//// Config
//// --------------------------------------------------------------------------------------
//
///**
// * @brief Configuration for path following controller.
// *
// * Notes:
// * - Linear PI is applied to "distance to carrot" (bounded by lookahead), mainly for smooth speed buildup.
// *   You can also set ki_linear=0 and rely on speed laws only.
// * - Angular PI tracks heading to carrot. Speed is additionally limited by yaw-rate demand based on curvature estimate.
// * - End-of-path braking is distance-based (no time scaling).
// * - Rate limits are strongly recommended for inverted pendulum safety.
// */
//struct bilbo_position_control_config_t {
//    // --- PI gains (same spirit as your original) ---
//    float kp_linear;
//    float ki_linear;
//
//    float kp_angular;
//    float ki_angular;
//
//    // --- timing ---
//    float Ts;
//
//    // --- lookahead: L(v) = clamp(L_min + L_gain*|v|, L_min, L_max) ---
//    float lookahead_min;   // [m]
//    float lookahead_max;   // [m]
//    float lookahead_gain;  // [s] (since gain multiplies m/s -> m)
//
//    // --- default saturation limits ---
//    float max_speed_forward; // [m/s]
//    float max_speed_turn;    // [rad/s]
//
//    // --- path tracking semantics ---
//    float gate_default_radius;      // [m] used for backwards compatible single-point (GATE)
//    float advance_hysteresis;       // [m] helps prevent rapid back/forth segment switching
//
//    // --- end-of-path completion ---
//    float final_arrival_tolerance;  // [m] distance to final waypoint to be considered "inside"
//    float arrival_time;             // [s] must remain inside continuously
//    float end_decel;                // [m/s^2] braking capability used for v<=sqrt(2*a*d_remain)
//
//    // --- yaw-rate demand speed limiting (pure pursuit curvature estimate) ---
//    float kappa_epsilon;            // small number to avoid division by zero
//    float min_speed_yaw_limit;      // [m/s] floor so it doesn't stall too early
//    float heading_cos_min;          // [0..1] minimum cos scaling (0 keeps your "never reverse due to heading")
//
//    // --- optional corner slowdown (polyline based) ---
//    float corner_approach_dist;     // [m] start slowing when within this distance to next vertex
//    float corner_speed_reduction_max; // [0..1] maximum fraction of v_max reduced at a 180deg turn
//
//    // --- command shaping (rate limits) ---
//    float max_accel;                // [m/s^2] limit on v_cmd change rate
//    float max_yaw_accel;            // [rad/s^2] limit on psi_dot_cmd change rate
//
//    // --- allow reverse driving? (optional; off by default for inverted pendulum) ---
//    uint8_t allow_reverse;          // 0/1
//    float backwards_switch_angle;   // [rad] if |angle_to_target - psi| > this -> reverse
//};
//
//// --------------------------------------------------------------------------------------
//// Telemetry / debug
//// --------------------------------------------------------------------------------------
//
//enum class bilbo_position_control_mode_t : uint8_t {
//    NONE = 0,
//    PATH_FOLLOW = 1,
//    POSITION_TO_POINT = 2, // compatibility wrapper around PATH_FOLLOW with single GATE waypoint
//};
//
//struct bilbo_position_control_data_t {
//    bilbo_position_control_mode_t current_mode;
//    bilbo_position_control_output_t current_output;
//    bool is_executing_command;
//
//    // simple path follower status
//    uint16_t active_command_id;
//    uint16_t queued_waypoints;
//    uint16_t current_segment_index;
//    float lookahead_current;
//    float remaining_path_length;
//    bool inside_final_region;
//};
//
//// --------------------------------------------------------------------------------------
//// Callbacks
//// --------------------------------------------------------------------------------------
//
//struct bilbo_position_control_callbacks_t {
//    core_utils_CallbackContainer<4, uint16_t> element_finished;
//    core_utils_CallbackContainer<4, uint16_t> element_timeout;
//};
//
//// --------------------------------------------------------------------------------------
//// Main class
//// --------------------------------------------------------------------------------------
//
//class BILBO_PositionControl {
//public:
//    static constexpr uint16_t WAYPOINT_BUFFER_SIZE = 64;
//
//    BILBO_PositionControl();
//
//    bilbo_position_control_output_t update(bilbo_position_state_t current_state);
//
//    void set_config(bilbo_position_control_config_t config);
//    bilbo_position_control_config_t get_config();
//    void reset();
//
//    // --- Path interface (new) ---
//    void clear_path();
//    bool append_waypoint(const bilbo_waypoint_t& wp);
//    bool append_shape(float x, float y);
//    bool append_gate(float x, float y, float radius_m);
//    uint16_t queued_waypoints() const;
//
//    /**
//     * @brief Start executing the currently queued path.
//     * @param command_id Used in finished/timeout callbacks.
//     * @param timeout_s If >0, abort after timeout seconds.
//     * @param max_speed_override If >0, saturate v_cmd by this, else config.max_speed_forward.
//     */
//    bool start_path(uint16_t command_id, float timeout_s, float max_speed_override);
//
//    void abort_current_command();
//    bool is_executing_command() const;
//
//    // --- Backwards compatible single point command ---
//    bool set_position_command(position_command_t command);
//
//    bool is_finished() const { return !is_executing_command(); }
//    bilbo_position_control_data_t get_data() const;
//
//    bilbo_position_control_callbacks_t callbacks;
//
//private:
//    // --- internal helpers ---
//    void _on_command_finished();
//    void _on_timeout();
//
//    // core path follower tick
//    bilbo_position_control_output_t _follow_path_tick(bilbo_position_state_t st);
//
//    // ring buffer ops
//    bool _wp_push(const bilbo_waypoint_t& wp);
//    bool _wp_pop_front();
//    const bilbo_waypoint_t* _wp_peek(uint16_t idx_from_front) const;
//
//    // geometry helpers
//    static float _clampf(float v, float lo, float hi);
//    static float _wrapToPi(float a);
//    static float _hypot(float x, float y);
//
//    // compute closest point projection onto segment AB; returns t in [0,1] and closest point C
//    static float _project_point_to_segment(float px, float py,
//                                           float ax, float ay, float bx, float by,
//                                           float& cx, float& cy);
//
//    // compute lookahead point along polyline starting at current segment with progress t0
//    bool _compute_carrot(bilbo_position_state_t st,
//                         float lookahead_L,
//                         float& carrot_x, float& carrot_y,
//                         float& remaining_path_len,
//                         uint16_t& seg_index_out,
//                         float& seg_t_out);
//
//    // compute corner speed reduction factor (0..1 reduction fraction)
//    float _corner_speed_reduction(bilbo_position_state_t st,
//                                  uint16_t seg_index,
//                                  float dist_to_vertex) const;
//
//private:
//    bilbo_position_control_config_t config{};
//    bilbo_position_control_mode_t current_mode{bilbo_position_control_mode_t::NONE};
//
//    // --- active command bookkeeping ---
//    uint16_t _active_command_id{0};
//    float _active_timeout_s{0.0f};
//    float _active_max_speed{0.0f}; // <=0 => use config.max_speed_forward
//    uint32_t _command_start_tick{0};
//
//    // --- PI integrators ---
//    float _pos_i{0.0f};
//    float _ang_i{0.0f};
//
//    // --- arrival-hold for end of path ---
//    float _arrival_hold_time{0.0f};
//    bool _inside_final{false};
//
//    // --- command shaping ---
//    float _v_prev{0.0f};
//    float _w_prev{0.0f};
//
//    // --- path progress state ---
//    uint16_t _segment_index{0}; // index into path polyline vertices (front-relative)
//    float _seg_t{0.0f};         // progress along current segment [0..1]
//
//    // --- waypoint ring buffer ---
//    bilbo_waypoint_t _wp_buf[WAYPOINT_BUFFER_SIZE]{};
//    uint16_t _wp_head{0};
//    uint16_t _wp_tail{0};
//    uint16_t _wp_count{0};
//
//    // telemetry
//    bilbo_position_control_data_t _data{};
//};
//
//#endif /* CONTROL_BILBO_POSITION_CONTROL_H_ */
