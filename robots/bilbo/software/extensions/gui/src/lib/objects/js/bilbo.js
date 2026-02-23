import {Widget} from "../objects.js";
import {getColor, shadeColor} from "../../helpers.js";
import '../../styles/bilbo.css';
import {DigitalNumberWidget, LineScrollTextWidget, StatusWidget} from "./text.js";
import {ButtonWidget, MultiStateButtonWidget} from "./buttons.js";
import {
    BatteryIndicatorWidget,
    ConnectionIndicator,
    InternetIndicator,
    JoystickIndicator,
    NetworkIndicator
} from "./indicators.js";


export class BILBO_Drawing {
    constructor(id, config = {}) {
        const defaults = {
            wheel_diameter: 0.14,   // m
            body_height: 0.19,    // m from wheel center to body top
            body_width: 0.1,    // m
            tire_width: 0.02,   // m

            tire_color: [0, 0, 0, 1],
            wheel_color: [0.8, 0.8, 0.8, 1],
            body_color: [0.7, 0, 0, 0.8],
            body_outline_color: [0.1, 0.1, 0.1, 1],

            draw_vertical_line: true,
            draw_ground: true,
            ground_color: [0.3, 0.3, 0.3, 1],
            ground_margin: 0.17,
        };

        this.id = id;
        this.config = {...defaults, ...config};
        this.data = {theta: 0};  // radians

        this.state = {
            filtered_velocity: 0,
            prev_velocity: 0
        };
        this.element = this._initElement();
    }

    _computeViewBox(containerWidthPx, containerHeightPx) {
        const c = this.config;
        const r = c.wheel_diameter / 2;

        const ground_margin = c.ground_margin || 0;
        const content_width = Math.max(c.body_width, c.wheel_diameter) + 2 * c.tire_width;
        const robot_height = r + c.body_height + (c.draw_ground ? c.tire_width : 0);

        const aspect = containerWidthPx / containerHeightPx;
        const margin_top_ratio = 0.1;  // 10% breathing room

        // Total viewBox height includes top margin
        this.vh = robot_height * (1 + margin_top_ratio);
        // ViewBox width matches container aspect ratio
        this.vw = this.vh * aspect;

        // Horizontal center
        this.vx = -this.vw / 2;
        // Vertical position so ground (r) is just above bottom
        this.vy = r - this.vh + c.tire_width;
    }


    _initElement() {
        const wrapper = document.createElement("div");
        wrapper.id = this.id;
        wrapper.classList.add("bilbo-drawing");

        const SVG_NS = "http://www.w3.org/2000/svg";
        const svg = document.createElementNS(SVG_NS, "svg");
        wrapper.appendChild(svg);
        this._svg = svg;
        return wrapper;
    }

    attach(container) {
        this.container = container;
        container.appendChild(this.element);
        return this;
    }

    update(data) {
        Object.assign(this.data, data);

        const v = data.velocity || 0;
        const alpha = 0.1;

        // High-pass filter: only keep velocity changes
        const prev_v = this.state.prev_velocity;
        const prev_fv = this.state.filtered_velocity;
        const filtered_v = alpha * (prev_fv + v - prev_v);

        this.state.filtered_velocity = filtered_v;
        this.state.prev_velocity = v;

        this.draw();
    }


    draw() {
        const rect = this.container.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) return;

        this._computeViewBox(rect.width, rect.height);
        this._svg.setAttribute("viewBox", `${this.vx} ${this.vy} ${this.vw} ${this.vh}`);

        const c = this.config;
        const theta = (this.data.theta * 180) / Math.PI;  // deg
        const r = c.wheel_diameter / 2;
        const tw = c.tire_width;
        const bh = c.body_height;
        const bw = c.body_width;

        // --- Calculate horizontal offset from filtered velocity ---
        const horizontal_offset = this.state.filtered_velocity * 0.2; // adjust 0.2 as needed
        // const horizontal_offset = 0.1;

        const svg = this._svg;
        while (svg.firstChild) svg.removeChild(svg.firstChild);

        const ns = "http://www.w3.org/2000/svg";

        // Main group for horizontal motion
        const mainG = document.createElementNS(ns, "g");
        mainG.setAttribute("transform", `translate(${horizontal_offset}, 0)`);
        svg.appendChild(mainG);

        // 1) ground (full width)
        if (c.draw_ground) {
            const ground = document.createElementNS(ns, "rect");
            // ground.setAttribute("x", this.vx - horizontal_offset); // keep ground static
            ground.setAttribute("x", this.vx); // keep ground static
            ground.setAttribute("y", r);
            ground.setAttribute("width", this.vw);
            ground.setAttribute("height", tw);
            ground.setAttribute("fill", getColor(c.ground_color));
            svg.appendChild(ground);
        }

        // 2) body (behind wheels)
        const bodyG = document.createElementNS(ns, "g");
        bodyG.setAttribute("transform", `rotate(${theta})`);
        const body = document.createElementNS(ns, "rect");
        body.setAttribute("x", -bw / 2);
        body.setAttribute("y", -bh);
        body.setAttribute("width", bw);
        body.setAttribute("height", bh);
        body.setAttribute("fill", getColor(c.body_color));
        body.setAttribute("stroke", getColor(c.body_outline_color));
        body.setAttribute("stroke-width", tw / 2);
        body.setAttribute("rx", tw); // rounded corners
        bodyG.appendChild(body);
        mainG.appendChild(bodyG);

        // 4) vertical / lean lines (slightly longer than body)
        if (c.draw_vertical_line) {
            const lineLen = bh * 1.1;   // 10% longer

            // reference vertical (dotted)
            const v = document.createElementNS(ns, "line");
            v.setAttribute("x1", 0);
            v.setAttribute("y1", 0);
            v.setAttribute("x2", 0);
            v.setAttribute("y2", -lineLen);
            v.setAttribute("stroke", getColor(c.body_outline_color));
            v.setAttribute("stroke-width", tw / 8);
            v.setAttribute("stroke-dasharray", `${tw / 4},${tw / 8}`);
            mainG.appendChild(v);

            // lean line
            const l = document.createElementNS(ns, "line");
            l.setAttribute("x1", 0);
            l.setAttribute("y1", 0);
            l.setAttribute("x2", 0);
            l.setAttribute("y2", -lineLen);
            l.setAttribute("transform", `rotate(${theta})`);
            l.setAttribute("stroke", getColor(c.body_outline_color));
            l.setAttribute("stroke-width", tw / 8);
            l.setAttribute("stroke-dasharray", `${tw / 4},${tw / 8}`);
            mainG.appendChild(l);
        }

        // 3) wheels (on top of body)
        const outer = document.createElementNS(ns, "circle");
        outer.setAttribute("cx", 0);
        outer.setAttribute("cy", 0);
        outer.setAttribute("r", r);
        outer.setAttribute("fill", getColor(c.tire_color));
        mainG.appendChild(outer);

        const inner = document.createElementNS(ns, "circle");
        inner.setAttribute("cx", 0);
        inner.setAttribute("cy", 0);
        inner.setAttribute("r", r - tw);
        inner.setAttribute("fill", getColor(c.wheel_color));
        mainG.appendChild(inner);
    }

}

export class BILBO_OverviewWidget extends Widget {
    constructor(id, config = {}) {
        super(id, config);

        const default_configuration = {
            id: 'bilbo1',
            id_number: 0,
            color: [1, 1, 1, 1],
        }

        this.configuration = {...default_configuration, ...this.configuration};

        this.element = this.initializeElement();
        this.configureElement(this.element);
        this.assignListeners(this.element);


        this.drawing = new BILBO_Drawing(this.id, {body_color: this.configuration.color});
        this.drawing.attach(this.drawing_cointer);


        // // Animation setup
        // let theta = Math.PI / 2;
        // let direction = -1;
        // const speed = 1.0; // radians per second
        // const minTheta = -Math.PI / 2;
        // const maxTheta = Math.PI / 2;
        //
        // const animate = (timestamp) => {
        //     if (!animate.lastTime) animate.lastTime = timestamp;
        //     const delta = (timestamp - animate.lastTime) / 1000;
        //     animate.lastTime = timestamp;
        //
        //     // Update angle
        //     theta += direction * speed * delta;
        //
        //     // Bounce
        //     if (theta <= minTheta) {
        //         theta = minTheta;
        //         direction = 1;
        //     } else if (theta >= maxTheta) {
        //         theta = maxTheta;
        //         direction = -1;
        //     }
        //
        //     this.drawing.update({theta});
        //     requestAnimationFrame(animate);
        // };

        requestAnimationFrame(() => {
            this.drawing.update({theta: Math.PI / 4});
        });
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    initializeElement() {
        const element = document.createElement('div');
        element.id = this.id;
        element.classList.add('widget', 'bilbo-overview-widget');

        this.top = document.createElement('div');
        this.top.classList.add('top');
        element.appendChild(this.top);

        // Create the logo
        const logo = document.createElement('div');
        logo.classList.add('logo');
        this.top.appendChild(logo);

        const logo_img = document.createElement('img')
        logo_img.src = new URL('../../assets/bilbo_logo.png', import.meta.url).href
        logo_img.alt = 'Logo'
        logo_img.className = 'bilbo_logo'
        logo.appendChild(logo_img)


        this.id_container = document.createElement('div');
        this.id_container.classList.add('id_container');
        this.top.appendChild(this.id_container);


        this.id_number = document.createElement('span');
        this.id_number.classList.add('seven-seg-digit');
        this.id_number.textContent = String(this.configuration.id_number || '0');
        this.id_number.style.color = getColor(this.configuration.color || [0, 0, 0, 1])
        this.id_container.appendChild(this.id_number);

        // const ro = new ResizeObserver(entries => {
        //     for (let {contentRect: r} of entries) {
        //         // pick 0.85 to leave a little padding
        //         const size = 0.85 * Math.min(r.width, r.height);
        //         span.style.fontSize = `${size}px`;
        //     }
        //     this.drawing.draw();
        // });
        // ro.observe(this.id_container);

        this.top_widget_container = document.createElement('div');
        this.top_widget_container.classList.add('widgets');
        this.top.appendChild(this.top_widget_container);

        // Add 6 placeholders to the top widget container
        for (let i = 0; i < 0; i++) {
            const widget = document.createElement('div');
            widget.classList.add('top-placeholder');
            this.top_widget_container.appendChild(widget);
        }

        this.joystick_indicator = new JoystickIndicator('joystick', {config: {available: true}})
        this.joystick_indicator.element.style.gridColumnStart = '1';
        this.joystick_indicator.element.style.gridColumnEnd = '2';
        this.top_widget_container.appendChild(this.joystick_indicator.getElement());

        this.network_indicator = new NetworkIndicator('network', {config: {}})
        this.network_indicator.element.style.gridColumnStart = '2';
        this.network_indicator.element.style.gridColumnEnd = '3';
        this.top_widget_container.appendChild(this.network_indicator.getElement());


        this.connection_indicator = new ConnectionIndicator('connection', {config: {}})
        this.connection_indicator.element.style.gridColumnStart = '3';
        this.connection_indicator.element.style.gridColumnEnd = '4';
        this.top_widget_container.appendChild(this.connection_indicator.getElement());


        this.internet_indicator = new InternetIndicator('internet', {config: {available: true}})
        this.internet_indicator.element.style.gridColumnStart = '4';
        this.internet_indicator.element.style.gridColumnEnd = '5';
        this.top_widget_container.appendChild(this.internet_indicator.getElement());

        this.battery_indicator = new BatteryIndicatorWidget('battery', {
            config: {
                show: 'voltage',
                label_position: 'center',
                value: 0.95
            }
        });

        this.battery_indicator.element.style.gridColumnStart = '5';
        this.battery_indicator.element.style.gridColumnEnd = '7';
        this.top_widget_container.appendChild(this.battery_indicator.getElement());

        // -------------------------------------------------------------------------------------------------------------


        this.bottom = document.createElement('div');
        this.bottom.classList.add('bottom');
        element.appendChild(this.bottom);

        this.status_container = document.createElement('div');
        this.status_container.classList.add('status');
        this.bottom.appendChild(this.status_container);


        const status_widget = new StatusWidget('status', {
            config: {
                elements: {
                    'status': {
                        label: 'Status',
                        color: [0, 0.9, 0, 1],
                        status: 'ok',
                        label_color: [0.8, 0.8, 0.8, 1],
                        status_color: [0, 0.9, 0, 1],
                    },
                    'control': {
                        label: 'Control',
                        color: [0, 0.9, 0, 1],
                        status: 'balancing',
                        label_color: [0.8, 0.8, 0.8, 1],
                        status_color: [0, 0.9, 0, 1],
                    },
                    'mode': {
                        label: 'Mode',
                        color: [0.5, 0.5, 0.5, 1],
                        status: 'none',
                        label_color: [0.8, 0.8, 0.8, 1],
                        status_color: [0.5, 0.5, 0.5, 1],
                    }
                }
            }
        });

        status_widget.attach(this.status_container);

        this.bottom_buttons = document.createElement('div');
        this.bottom_buttons.classList.add('bottom_buttons');
        this.bottom.appendChild(this.bottom_buttons);

        this.line_terminal = new LineScrollTextWidget('terminal', {config: {}});

        // Make it 2 grid columns wide
        this.line_terminal.getElement().style.gridColumnStart = '1';
        this.line_terminal.getElement().style.gridColumnEnd = '3';

        this.bottom.appendChild(this.line_terminal.getElement());


        this.mode_button = new MultiStateButtonWidget('mode', {
                config: {
                    title: 'Mode',
                    states: ['off', 'balancing'],
                }
            }
        )

        this.mode_button.attach(this.bottom_buttons);

        this.mode_button.callbacks.get('click').register(event => {
            this.callbacks.get('event').call({
                id: this.id,
                event: 'mode_button_click',
                data: {}
            });
        })

        this.link_button = new ButtonWidget('link', {
            config: {
                icon: '🔗',
                icon_size: 15,
            }
        });

        this.link_button.attach(this.bottom_buttons);

        this.link_button.callbacks.get('click').register(event => {
            this.callbacks.get('event').call({
                id: this.id,
                event: 'link_button_click',
                data: {}
            });
        })

        this.drawing_cointer = document.createElement('div');
        this.drawing_cointer.classList.add('drawing');
        element.appendChild(this.drawing_cointer);


        this.data_container = document.createElement('div');
        this.data_container.classList.add('data');
        element.appendChild(this.data_container);

        this.drawDataContainer();

        return element;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    resize() {
        if (this.id_container && this.id_number) {
            const r = this.id_container.getBoundingClientRect();
            const size = Math.floor(0.85 * Math.min(r.width, r.height)); // leave a bit of padding
            this.id_number.style.fontSize = `${size}px`;
        }

        this.drawing?.draw();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    configureElement(element) {
        super.configureElement(element);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    drawDataContainer() {
        const data_widgets = {};

        const x_widget = new DigitalNumberWidget('x', {
            config: {
                min_value: -10,
                max_value: 10,
                value: 0,
                increment: 0.1,
                title: 'x',
                title_position: 'left'
            }
        });

        data_widgets['x'] = x_widget;
        this.data_container.appendChild(x_widget.getElement());

        const y_widget = new DigitalNumberWidget('x', {
            config: {
                min_value: -10,
                max_value: 10,
                value: 0,
                increment: 0.1,
                title: 'y',
                title_position: 'left'
            }
        });
        data_widgets['y'] = y_widget;
        this.data_container.appendChild(y_widget.getElement());

        const v_widget = new DigitalNumberWidget('x', {
            config: {
                min_value: -10,
                max_value: 10,
                value: 0,
                increment: 0.1,
                title: 'v',
                title_position: 'left'
            }
        });
        data_widgets['v'] = v_widget;
        this.data_container.appendChild(v_widget.getElement());

        const theta_widget = new DigitalNumberWidget('x', {
            config: {
                min_value: -100,
                max_value: 100,
                value: 0,
                increment: 0.1,
                title: 'theta',
                title_position: 'left'
            }
        });
        data_widgets['theta'] = theta_widget;
        this.data_container.appendChild(theta_widget.getElement());

        const theta_dot_widget = new DigitalNumberWidget('x', {
            config: {
                min_value: -10,
                max_value: 10,
                value: 0,
                increment: 0.1,
                title: 'theta_d',
                title_position: 'left'
            }
        });
        data_widgets['theta_dot'] = theta_dot_widget;
        this.data_container.appendChild(theta_dot_widget.getElement());

        const psi_widget = new DigitalNumberWidget('x', {
            config: {
                min_value: -100,
                max_value: 100,
                value: 0,
                increment: 0.1,
                title: 'psi',
                title_position: 'left'
            }
        });
        data_widgets['psi'] = psi_widget;
        this.data_container.appendChild(psi_widget.getElement());
        const psi_dot_widget = new DigitalNumberWidget('x', {
            config: {
                min_value: -100,
                max_value: 100,
                value: 0,
                increment: 0.1,
                title: 'psi_d',
                // title_is_latex: true,
                title_position: 'left'
            }
        });
        data_widgets['psi_dot'] = psi_dot_widget;
        this.data_container.appendChild(psi_dot_widget.getElement());
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    assignListeners(element) {
        super.assignListeners(element);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    getElement() {
        return this.element;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    update(data) {
        const {x, y, v, theta, theta_dot, psi, psi_dot} = data;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    updateConfig(data) {
        this.configuration = {...this.configuration, ...data};
        this.configureElement(this.element);
    }
}