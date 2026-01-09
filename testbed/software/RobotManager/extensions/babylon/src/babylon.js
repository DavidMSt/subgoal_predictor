import {
    ArcRotateCamera,
    DirectionalLight,
    GlowLayer,
    HemisphericLight,
    PointerEventTypes,
    Scene as BabylonScene,
    ShadowGenerator,
    Vector3,
} from "@babylonjs/core";

// import {VideoRecorder} from "@babylonjs/core/Misc/videoRecorder";

import {VideoRecorder} from '@babylonjs/core';

/* === CUSTOM IMPORTS =============================================================================================== */
import {Websocket} from "./lib/websocket.js"
import {
    coordinatesFromBabylon,
    coordinatesToBabylon,
    getBabylonColor,
    getBabylonColor3,
    Scene
} from "./lib/babylon_utils.js"

import {drawCoordinateSystem} from "./lib/objects/coordinate_system.js";
import {BabylonSimpleFloor} from "./lib/objects/floor/floor.js";
import {BabylonBox, BabylonWall_Fancy} from "./lib/objects/box/box.js";
import {Quaternion} from "./lib/quaternion.js";
import {BabylonObject, BabylonObjectGroup} from "./lib/objects.js";
import {BabylonBilbo, BabylonBilboRealistic, BabylonSimpleBilbo} from "./lib/objects/bilbo/bilbo.js";

import {BABYLON_OBJECT_MAPPINGS} from "./lib/objects/mapping.js"
import {
    Callbacks,
    deg2rad,
    getColor,
    removeLeadingAndTrailingSlashes,
    splitPath,
    stringifyObject
} from "../../gui/src/lib/helpers.js"
import './babylon.css'


/* === EXTERNAL CUSTOM IMPORTS ====================================================================================== */
import "../../gui/src/lib/styles/widget-styles.css"
import "../../gui/src/lib/styles/context_menu.css"
import {ButtonWidget} from "../../gui/src/lib/objects/js/buttons.js";
import {LineScrollTextWidget} from "../../gui/src/lib/objects/js/text.js";
import {ContextMenuItem} from "../../gui/src/lib/objects/contextmenu.js";
import {BabylonCircleDrawing, BabylonLineDrawing, BabylonRectangleDrawing} from "./lib/objects/drawings";
import {ArucoStatic} from "./lib/objects/static/static";
import {BabylonFrodo} from "./lib/objects/frodo/frodo";

/* === HELPERS ====================================================================================================== */
function _chooseBestMime() {
    const c = [
        "video/webm;codecs=vp9",
        "video/webm;codecs=vp8",
        "video/webm;codecs=h264", // not everywhere, but sometimes available
        "video/webm"
    ];
    return c.find(t => window.MediaRecorder?.isTypeSupported?.(t)) || "video/webm";
}


/* ================================================================================================================== */
export class Babylon extends Scene {
    is_recording = false;
    // Sliding-window message rate tracker (5s window)
    _msgTimes = [];      // monotonically growing array of timestamps (ms)
    _msgHead = 0;       // index of first still-valid timestamp within _msgTimes

    _resizeArmed = false;

    constructor(id, canvasOrEngine, config = {}, objects = {}) {
        super(canvasOrEngine);

        const default_config = {
            websocket_host: 'localhost',
            websocket_port: '9000',
            coordinate_system_length: 0.5,
            show_coordinate_system: true,


            background_color: [31 / 255, 32 / 255, 35 / 255],
            ambient_color: [0.5, 0.5, 0.5],

            scene: {
                add_fog: true,
                fog_color: [31 / 255, 32 / 255, 35 / 255],
                fog_density: 0.08,
                fog_mode: 'exp2',
            },

            camera: {
                position: [2, -2, 1],
                target: [0, 0, 0],
                alpha: deg2rad(-18),
                beta: deg2rad(70),
                radius: 3.5,
                fov: deg2rad(65),
                radius_lower_limit: 0.5,
                radius_upper_limit: 6,
            },
            lights: {
                hemispheric_direction: [2, -1, 0]
            },
            ui: {
                text_color: [1, 1, 1],
                font_size: 40,
            }

        }

        this.config = {...default_config, ...config};
        this.id = id;
        this.objects = {}

        this.canvas = canvasOrEngine;

        console.log('babylon config')
        console.log(config)

        // element.addEventListener('mousedown', e => e.preventDefault()); // stops focus
        this._initializeWebsocket();
        this._addSceneClickListener();
        this._initializeScene();

        this.objects = objects;
        this._buildObjectsFromConfig(objects);

        this.callbacks = new Callbacks();
        this.callbacks.add('event');
        this.callbacks.add('log');
        this.callbacks.add('initialized')

        this.callbacks.add('record_start');
        this.callbacks.add('record_stop');
        this.callbacks.add('websocket_connected');
        this.callbacks.add('websocket_disconnected');

        this._addOwnCallbacks();
        // this.addTestObjects();


        setTimeout(() => {
            this.log(`Babylon scene initialized. Listening on websocket ${this.config.websocket_host}:${this.config.websocket_port}...`);
        }, 250);

        setTimeout(() => {
            this.callbacks.get('initialized').call();
        }, 500);
    }

    /* === METHODS ================================================================================================== */
    addObject(object) {
        // Check if the object id is already in objects
        if (object.id in this.objects) {
            console.warn(`Object with id ${object.id} already exists`);
            return;
        }

        if (!(object instanceof BabylonObject)) {
            console.warn(`Object is not a BabylonObject`);
            return;
        }

        this.objects[object.id] = object;
        object.parent = this;
        object.callbacks.get('event').register(this._onObjectEvent.bind(this));
        object.callbacks.get('log').register(this._onObjectLog.bind(this));
        object.callbacks.get('send_message').register(this._onObjectSendMessage.bind(this));
        console.log(`BABYLON: Added object with id ${object.id}`);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    removeObject(object) {

        // CHeck if object is a string
        if (typeof object === 'string') {
            object = this.getObjectByUID(object);
            if (!object) {
                console.warn(`Object with id ${object} does not exist`);
                return;
            }
        }
        if (object.id in this.objects) {
            delete this.objects[object.id];
        } else {
            console.warn(`Object with id ${object.id} does not exist`);
        }

        object.delete();
        this.log(`Object ${object.id} removed`, 'warning');
    }

    reset() {
        // Loop through all objects and remove them
        for (const [key, value] of Object.entries(this.objects)) {
            this.removeObject(value);
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    send(msg) {
        this.websocket.send(msg);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    sendEvent(event, id = null) {
        const message = {
            type: 'event',
            id: id,
            event: event,
        }
        this.send(message);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    getObjectByUID(uid) {

        uid = removeLeadingAndTrailingSlashes(uid);

        let first_part, remainder;
        [first_part, remainder] = splitPath(uid);

        if (first_part !== this.id) {
            this.log(`getObjectByUID: ${uid} does not match this.id: ${this.id}`);
            return null;
        }
        if (!remainder) {
            return this;
        }

        [first_part, remainder] = splitPath(remainder);

        first_part = `${this.id}/${first_part}`

        if (first_part in this.objects) {
            if (!remainder) {
                return this.objects[first_part];
            } else {
                if (this.objects[first_part] instanceof BabylonObjectGroup) {
                    return this.objects[first_part].getObjectByPath(remainder);
                } else {
                    return null;
                }
            }
        }
        return null;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    setCamera() {

    }

    /* -------------------------------------------------------------------------------------------------------------- */
    setArcRotateCamera(position, target, alpha, beta, radius) {
        this.camera.setPosition(coordinatesToBabylon(position));
        this.camera.setTarget(coordinatesToBabylon(target));
        this.camera.alpha = alpha;
        this.camera.beta = beta;
        this.camera.radius = radius;
    }

    /* -------------------------------------------------------------------------------------------------------------- */

    /* -------------------------------------------------------------------------------------------------------------- */
    getBabylonVisualization() {
        return this;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    getDebugData() {
        const data = {};
        const scene = this.scene;
        const cam = scene?.activeCamera || this.camera;

        const safeVec = (v) => v ? [Number(v.x || 0), Number(v.y || 0), Number(v.z || 0)] : null;
        const deg = (r) => (r != null ? (r * 180 / Math.PI) : null);

        if (!cam) {
            data.camera = {present: false};
            return data;
        }

        const type = (typeof cam.getClassName === 'function') ? cam.getClassName() : (cam.constructor?.name || 'Camera');
        const isTargetCam = (cam.getTarget && typeof cam.getTarget === 'function');
        const hasRotation = !!cam.rotation || !!cam.rotationQuaternion;

        // Common camera info
        const common = {
            present: true,
            type,
            name: cam.name ?? null,
            id: cam.id ?? null,
            uniqueId: cam.uniqueId ?? null,
            mode: cam.mode === 1 ? "ORTHOGRAPHIC" : "PERSPECTIVE",
            fov_deg: cam.mode === 1 ? null : (cam.fov ? deg(cam.fov) : null),

            // Ortho params (useful if mode=ORTHOGRAPHIC)
            orthoLeft: cam.orthoLeft ?? null,
            orthoRight: cam.orthoRight ?? null,
            orthoTop: cam.orthoTop ?? null,
            orthoBottom: cam.orthoBottom ?? null,

            minZ: cam.minZ ?? null,
            maxZ: cam.maxZ ?? null,
            inertia: cam.inertia ?? null,
            position: coordinatesFromBabylon(safeVec(cam.position)),
            target: isTargetCam ? coordinatesFromBabylon(safeVec(cam.getTarget())) : null,
            upVector: coordinatesFromBabylon(safeVec(cam.upVector)),

            // Rotation (if available)
            rotation_euler_deg: (() => {
                if (cam.rotation) {
                    return [deg(cam.rotation.x), deg(cam.rotation.y), deg(cam.rotation.z)];
                }
                if (cam.rotationQuaternion && typeof cam.rotationQuaternion.toEulerAngles === 'function') {
                    const e = cam.rotationQuaternion.toEulerAngles();
                    return [deg(e.x), deg(e.y), deg(e.z)];
                }
                return null;
            })(),
        };

        // Type-specific
        const specific = {};

        // ArcRotateCamera
        if (type === "ArcRotateCamera") {
            specific.arcRotate = {
                alpha_deg: deg(cam.alpha),
                beta_deg: deg(cam.beta),
                radius: cam.radius ?? null,

                // limits
                lowerAlphaLimit_deg: cam.lowerAlphaLimit != null ? deg(cam.lowerAlphaLimit) : null,
                upperAlphaLimit_deg: cam.upperAlphaLimit != null ? deg(cam.upperAlphaLimit) : null,
                lowerBetaLimit_deg: cam.lowerBetaLimit != null ? deg(cam.lowerBetaLimit) : null,
                upperBetaLimit_deg: cam.upperBetaLimit != null ? deg(cam.upperBetaLimit) : null,
                lowerRadiusLimit: cam.lowerRadiusLimit ?? null,
                upperRadiusLimit: cam.upperRadiusLimit ?? null,

                // controls/sensitivities
                wheelPrecision: cam.wheelPrecision ?? null,
                wheelDeltaPercentage: cam.wheelDeltaPercentage ?? null,
                panningSensibility: cam.panningSensibility ?? null,
                angularSensibilityX: cam.angularSensibilityX ?? null,
                angularSensibilityY: cam.angularSensibilityY ?? null,

                // behaviors
                useAutoRotationBehavior: !!cam.useAutoRotationBehavior,
                useBouncingBehavior: !!cam.useBouncingBehavior,
                useFramingBehavior: !!cam.useFramingBehavior,

                // inertial offsets (if user is dragging the mouse)
                inertialAlphaOffset_deg: cam.inertialAlphaOffset != null ? deg(cam.inertialAlphaOffset) : null,
                inertialBetaOffset_deg: cam.inertialBetaOffset != null ? deg(cam.inertialBetaOffset) : null,
                inertialRadiusOffset: cam.inertialRadiusOffset ?? null,
                inertialPanningX: cam.inertialPanningX ?? null,
                inertialPanningY: cam.inertialPanningY ?? null,
            };
        }

        // FollowCamera (if you ever use it)
        if (type === "FollowCamera") {
            specific.follow = {
                lockedTarget: !!cam.lockedTarget,
                radius: cam.radius ?? null,
                heightOffset: cam.heightOffset ?? null,
                rotationOffset_deg: cam.rotationOffset != null ? deg(cam.rotationOffset) : null,
                cameraAcceleration: cam.cameraAcceleration ?? null,
                maxCameraSpeed: cam.maxCameraSpeed ?? null,
            };
        }

        // Free/Universal/Touch cameras share some stuff
        if (type === "FreeCamera" || type === "UniversalCamera" || type === "TouchCamera") {
            specific.freeLike = {
                speed: cam.speed ?? null,
                angularSensibility: cam.angularSensibility ?? null,
                keysUp: cam.keysUp ?? null,
                keysDown: cam.keysDown ?? null,
                keysLeft: cam.keysLeft ?? null,
                keysRight: cam.keysRight ?? null,
                ellipsoid: cam.ellipsoid ? safeVec(cam.ellipsoid) : null,
            };
        }

        data.camera = {...common, ...specific};
        return data;
    }

    getMessagesPerSecond(windowSeconds = 5) {
        const now = (typeof performance !== 'undefined' ? performance.now() : Date.now());
        const windowMs = Math.max(1, (windowSeconds ?? 5) * 1000);
        const cutoff = now - windowMs;

        // Prune anything outside the 5s window
        while (this._msgHead < this._msgTimes.length && this._msgTimes[this._msgHead] < cutoff) {
            this._msgHead++;
        }

        const count = this._msgTimes.length - this._msgHead;
        if (count <= 0) return 0;

        // During startup, only use the span we actually observed so far (grows up to windowMs)
        const firstTs = this._msgTimes[this._msgHead];
        const spanMs = Math.max(1, Math.min(windowMs, now - firstTs));

        // Use (N-1) / span to avoid overestimating with just 1–2 samples
        const intervals = Math.max(0, count - 1);
        const perSec = intervals / (spanMs / 1000);

        return Math.round(perSec);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    startRecording(fileName = "babylonjs.webm", maxDurationSeconds = 0 /* manual stop */, upscale = 1.0) {
        const engine = this.scene?.getEngine?.();
        if (!engine) {
            this.log("No engine for recording.", "error");
            return;
        }
        if (!VideoRecorder.IsSupported(engine)) {
            this.log("Video recording not supported in this browser.", "warning");
            return;
        }
        if (this.is_recording) {
            this.log("Already recording.", "warning");
            return;
        }

        // --- A) Render more pixels while recording ---
        this._prevScaling = engine.getHardwareScalingLevel?.() ?? 1;
        // Smaller number = more pixels. Halving -> 2x resolution; clamp to avoid insane values.
        const scaleDown = 1 / upscale; // 2× internal resolution during recording
        engine.setHardwareScalingLevel(Math.max(0.25, this._prevScaling * scaleDown));

        // --- B) Better codec + higher FPS (if the browser supports it) ---
        const options = {
            fps: 60,
            mimeType: _chooseBestMime(),       // try VP9/VP8/H264-in-webm
            recordChunckSize: 5_000_000        // bigger chunks = fewer file parts
        };

        this._videoRecorder = new VideoRecorder(engine, options);
        this.is_recording = true;
        this.log(`Started recording to "${fileName}" (fps=${options.fps}, mime=${options.mimeType}).`, "important");

        this.callbacks.get('record_start').call(fileName);
        // Save promise so we can clean up *after* finalize
        this._recordingPromise = this._videoRecorder
            .startRecording(fileName, maxDurationSeconds)
            .then((blob) => {
                this.log(`Recording finished (${Math.round((blob?.size || 0) / 1024)} KB).`, "important");

            })
            .catch((err) => this.log(`Recorder error: ${err}`, "error"))
            .finally(() => {
                // Restore resolution and dispose only after finalize
                try {
                    engine.setHardwareScalingLevel(this._prevScaling);
                } catch {
                }
                this._videoRecorder?.dispose?.();
                this._videoRecorder = null;
                this._recordingPromise = null;
                this.callbacks.get('record_stop').call();
            });
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    startRecordingHiBitrate(fileName = "babylonjs_highbit.webm", fps = 60, videoBitsPerSecond = 12_000_000) {
        const canvas = this.scene?.getEngine?.().getRenderingCanvas?.();
        if (!canvas) {
            this.log("No canvas for recording.", "error");
            return;
        }
        if (this.is_recording) {
            this.log("Already recording.", "warning");
            return;
        }

        // Render more pixels (same trick as above)
        const engine = this.scene.getEngine();
        this._prevScaling = engine.getHardwareScalingLevel?.() ?? 1;
        engine.setHardwareScalingLevel(Math.max(0.25, this._prevScaling * 0.5));

        const mime = _chooseBestMime();
        const stream = canvas.captureStream(fps);
        const rec = new MediaRecorder(stream, {mimeType: mime, videoBitsPerSecond});
        this._customRecorder = rec;
        this.is_recording = true;

        const chunks = [];
        rec.ondataavailable = (e) => {
            if (e.data?.size) chunks.push(e.data);
        };
        rec.onstop = () => {
            const blob = new Blob(chunks, {type: mime});
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = fileName;
            a.click();
            setTimeout(() => URL.revokeObjectURL(a.href), 5000);

            // restore
            try {
                engine.setHardwareScalingLevel(this._prevScaling);
                this.log("Setting back hardware scaling", "important");
            } catch {
                this.log("Failed to restore hardware scaling", "error");
            }
            this._customRecorder = null;
            this.is_recording = false;
            this.log(`High-bitrate recording saved (${Math.round(blob.size / 1024)} KB).`, "important");
            this.callbacks.get('record_stop').call();
        };
        rec.start(1000); // collect data every second
        this.log(`Started high-bitrate recording (fps=${fps}, ~${Math.round(videoBitsPerSecond / 1e6)} Mbps, ${mime}).`, "important");
        this.callbacks.get('record_start').call(fileName);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    stopRecording() {
        // Custom high-bitrate path?
        if (this._customRecorder) {
            try {
                this._customRecorder.stop();               // finalize async -> onstop handler does download + restore + callbacks
                this.log("Stopping high-bitrate recording…", "info");
            } catch (e) {
                this.log(`Stop error (hi-bitrate): ${e}`, "error");
            } finally {
                // Optional: reflect UI state immediately; finalize still fires record_stop later
                this.is_recording = false;
            }
            return true;
        }

        // Built-in Babylon VideoRecorder?
        if (this._videoRecorder) {
            try {
                this._videoRecorder.stopRecording();       // finalize async -> startRecording().finally handles dispose + restore + callbacks
                this.log("Stopping recording…", "info");
            } catch (err) {
                this.log(`Failed to stop recording: ${err}`, "error");
            } finally {
                this.is_recording = false;
            }
            return true;
        }

        this.log("No active recording.", "warning");
        return false;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    log(message, level = 'info') {

        // Check if message is an object
        if (typeof message === 'object') {
            message = stringifyObject(message, true);
        }

        this.callbacks.get('log').call(message, level);
    }

    /* === PRIVATE METHODS ========================================================================================== */
    _initializeWebsocket() {
        this.websocket = new Websocket({host: this.config.websocket_host, port: this.config.websocket_port});
        this.websocket.on('message', this._handleMessage.bind(this));
        this.websocket.on('connected', this._onWebsocketConnect.bind(this));
        this.websocket.on('close', this._onWebsocketDisconnected.bind(this));
        this.websocket.connect();
    }

    /* --------------------------------------------------------------------------------------------------------------- */
    _onWebsocketConnect() {
        this.callbacks.get('websocket_connected').call();
        this.log(`Websocket connected`)
    }

    /* --------------------------------------------------------------------------------------------------------------- */
    _onWebsocketDisconnected() {
        this.callbacks.get('websocket_disconnected').call();
        this.log(`Websocket disconnected`)
        this.reset();
    }

    /* --------------------------------------------------------------------------------------------------------------- */
    _addOwnCallbacks() {
        this.callbacks.get('record_start').register((fileName) => {
            const event = {
                'type': 'record_start',
                'data': {
                    'fileName': fileName
                }
            }
            this.sendEvent(event, this.id);
        });

        this.callbacks.get('record_stop').register(() => {
            const event = {
                'type': 'record_stop',
                'data': {}
            }
            this.sendEvent(event, this.id);
        });

    }

    /* --------------------------------------------------------------------------------------------------------------- */
    _handleMessage(msg) {
        this._trackIncomingMessage(); // For tracking how many messages we've received in the last second

        switch (msg.type) {
            case 'init':
                this._handleInitMessage(msg);
                break;
            case 'addObject':
                this._handleAddObjectMessage(msg);
                break;
            case 'removeObject':
                this._handleRemoveObjectMessage(msg);
                break;
            case 'update':
                this._handleUpdateMessage(msg);
                break;
            case 'updateObject':
                this._handleUpdateObjectMessage(msg);
                break;
            case 'updateObjectConfig':
                this._handleUpdateObjectConfigMessage(msg);
                break;
            case 'objectFunction':
                this._handleObjectFunctionMessage(msg);
                break;
            default:
                console.warn(`Unknown message type: ${msg.type}`);
                break;
        }
    }

    _trackIncomingMessage() {
        const now = (typeof performance !== 'undefined' ? performance.now() : Date.now());
        const WINDOW_MS = 5000;

        this._msgTimes.push(now);

        // Drop anything older than (now - 5s) by advancing the head
        const cutoff = now - WINDOW_MS;
        while (this._msgHead < this._msgTimes.length && this._msgTimes[this._msgHead] < cutoff) {
            this._msgHead++;
        }

        // Compact occasionally to avoid the array growing forever
        if (this._msgHead > 512 && this._msgHead > (this._msgTimes.length >> 1)) {
            this._msgTimes = this._msgTimes.slice(this._msgHead);
            this._msgHead = 0;
        }
    }

    /* --------------------------------------------------------------------------------------------------------------- */
    _handleInitMessage(msg) {
        this.log(`Received init message`)
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _buildObjectsFromConfig(objects) {
        // Loop through the objects keys and values
        for (const [key, value] of Object.entries(objects)) {
            const type = value.type;
            const object_class = BABYLON_OBJECT_MAPPINGS[type];
            if (!object_class) {
                this.log(`Unknown object type: ${type}`, "error");
                continue;
            }
            const object = new object_class(value.id, this, value);
            this.addObject(object);
        }
    }

    _buildObjectFromConfig(object_payload) {
        const type = object_payload.type;
        const object_class = BABYLON_OBJECT_MAPPINGS[type];
        if (!object_class) {
            this.log(`Unknown object type: ${type}`, "error");
            return;
        }
        const object = new object_class(object_payload.id, this, object_payload);
        this.addObject(object);
    }

    /* --------------------------------------------------------------------------------------------------------------- */
    _handleAddObjectMessage(msg) {
        this._buildObjectFromConfig(msg.payload);
    }

    /* --------------------------------------------------------------------------------------------------------------- */
    _handleRemoveObjectMessage(msg) {
        console.log(`Received remove object message:`);
        console.log(msg);
        this.removeObject(msg.id);
    }

    /* --------------------------------------------------------------------------------------------------------------- */
    _handleUpdateMessage(msg) {

        if (!('updates' in msg)) {
            this.log(`Received update message without message field: ${msg}`, "error");
            return;
        }

        for (const [id, update] of Object.entries(msg.updates)) {
            const object = this.getObjectByUID(id);
            if (!object) {
                this.log(`Received update for unknown object: ${id}`, "error");
                continue;
            }
            object.update(update)
        }

    }

    /* --------------------------------------------------------------------------------------------------------------- */
    _handleUpdateObjectMessage(msg) {
        this.log(`Received update object message:`);
        this.log(msg);
    }

    /* --------------------------------------------------------------------------------------------------------------- */
    _handleUpdateObjectConfigMessage(msg) {
        this.log(`Received update object config message:`);
        this.log(msg);
    }

    /* --------------------------------------------------------------------------------------------------------------- */
    _handleObjectFunctionMessage(msg) {
        this.log(`Received object function message:`);
        this.log(msg);
    }

    /* --------------------------------------------------------------------------------------------------------------- */
    // _addGlobalResizeListener() {
    //     // const engine = new Engine(this.canvas, true, {preserveDrawingBuffer: true, stencil: true});
    //     const engine = this.scene.getEngine();
    //
    //     // This ensures Babylon accounts for HiDPI / Retina displays
    //     engine.setHardwareScalingLevel(1 / window.devicePixelRatio);
    //
    //     // Resize on window change
    //     window.addEventListener("resize", () => {
    //         engine.resize();
    //     });
    // }

    _addGlobalResizeListener() {
        if (this._resizeArmed) return;    // <- guard
        this._resizeArmed = true;
        const engine = this.scene.getEngine();
        const canvas = engine.getRenderingCanvas();
        let lastDPR = -1;

        const applyDPRAndResize = () => {
            const dpr = Math.max(1, window.devicePixelRatio || 1);
            // Update hardware scaling **only if** DPR changed
            if (dpr !== lastDPR) {
                engine.setHardwareScalingLevel(1 / dpr);
                lastDPR = dpr;
            }

            // Make the backing store exactly CSS size * DPR (rounded to ints)
            const rect = canvas.getBoundingClientRect();
            const width = Math.max(1, Math.round(rect.width * dpr));
            const height = Math.max(1, Math.round(rect.height * dpr));

            // Only touch the engine if size actually changed (prevents extra frames)
            if (engine.getRenderWidth(true) !== width || engine.getRenderHeight(true) !== height) {
                engine.setSize(width, height, true);
            } else {
                // Still notify Babylon so projection matrices pick up aspect properly
                engine.resize(true);
            }
        };

        // 1) Window resize (covers most layout changes)
        window.addEventListener('resize', applyDPRAndResize);

        // 2) DPR/zoom changes (Chrome/Safari/Edge)
        if (window.matchMedia) {
            // Re-arm a new media query every time, since the expression uses the current DPR
            const armResolutionWatcher = () => {
                const mq = window.matchMedia(`(resolution: ${window.devicePixelRatio}dppx)`);
                const handler = () => {
                    mq.removeEventListener?.('change', handler);
                    armResolutionWatcher();
                    applyDPRAndResize();
                };
                mq.addEventListener?.('change', handler);
            };
            armResolutionWatcher();
        }

        // 3) VisualViewport scale changes (Safari/iPadOS often fires this)
        if (window.visualViewport) {
            window.visualViewport.addEventListener('resize', applyDPRAndResize);
            window.visualViewport.addEventListener('scroll', applyDPRAndResize); // some browsers signal zoom via “scroll”
        }

        // 4) Container resize (e.g. split pane, tabs, flexbox)
        if (typeof ResizeObserver !== 'undefined') {
            this._resizeObserver = new ResizeObserver(applyDPRAndResize);
            // Observe the canvas’ parent to catch layout changes
            const parent = canvas.parentElement || canvas;
            this._resizeObserver.observe(parent);
        }

        // Initial sizing
        applyDPRAndResize();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _initializeScene() {

        // — CAMERA —
        const camera = new ArcRotateCamera("Camera",
            this.config.camera.alpha, this.config.camera.beta,
            this.config.camera.radius, coordinatesToBabylon(this.config.camera.target), this.scene);

        camera.setPosition(coordinatesToBabylon(this.config.camera.position));
        camera.attachControl(this.canvas, true);
        camera.inputs.attached.keyboard.detachControl();
        camera.wheelPrecision = 100;
        camera.minZ = 0.1;
        camera.lowerBetaLimit = 0.0;            // optional: avoid exactly straight-down
        camera.upperBetaLimit = Math.PI / 2 - 0.05;    // never go below the ground plane
        camera.lowerRadiusLimit = this.config.camera.radius_lower_limit;
        camera.upperRadiusLimit = this.config.camera.radius_upper_limit;
        camera.fov = this.config.camera.fov;
        this.camera = camera;

        // this.framing = new FramingBehavior()
        // camera.addBehavior(this.framing);
        // this.framing.radiusScale = 1.2;       // padding around the mesh
        // this.framing.focusOnFramedObject = true;
        //
        // this.scene.animationsEnabled = true;
        // console.log(camera.getBehaviorByName("Framing"));  // should log your FramingBehavior instance


        // camera.onViewMatrixChangedObservable.add(() => {
        //     // serialize exactly the numbers you’ll want to hard‐code next time
        //     const cfg = {
        //         alpha: camera.alpha,
        //         beta: camera.beta,
        //         radius: camera.radius,
        //         target: [camera.target.x, camera.target.y, camera.target.z],
        //         position: [camera.position.x, camera.position.y, camera.position.z]
        //     };
        //     console.log("NEW CAMERA CONFIG:\n", JSON.stringify(cfg, null, 2));
        // });

        // now fence focus as desired (pick A or B)
        this.canvas.setAttribute('tabindex', '-1');           // A) unfocusable
// or
        this.canvas.tabIndex = 0;                             // B) keyboard ok
        this.canvas.addEventListener('mousedown', e => e.preventDefault(), {capture: true});

        // — LIGHT —
        new HemisphericLight("light", coordinatesToBabylon(this.config.lights.hemispheric_direction), this.scene).intensity = 0.5;
        new GlowLayer("glow", this.scene).intensity = 0.1;

        // - SHADOW -
        this.dirLight = new DirectionalLight(
            "shadowLight",
            new Vector3(0, 0, 0),
            this.scene
        );
        this.dirLight.position = coordinatesToBabylon([1, 1, 10]);
        this.dirLight.direction = coordinatesToBabylon([-1, -1, -1]);
        this.dirLight.intensity = 1.1;
        this.dirLight.shadowEnabled = true;

        this.shadowGen = new ShadowGenerator(1024, this.dirLight);
        this.scene.shadowGenerator = this.shadowGen;


        this.shadowGen.useExponentialShadowMap = true;
        this.shadowGen.depthScale = 200;                       // default is 50 — try 100–200
        this.shadowGen.forceBackFacesOnly = true;

        this.shadowGen.usePercentageCloserFiltering = true;     // PCF
        this.shadowGen.useContactHardeningShadowMap = true;     // optional, nicer penumbra
        this.shadowGen.filteringQuality = ShadowGenerator.QUALITY_HIGH;

        this.shadowGen.bias = 1e-6;      // start 0.0005 → 0.003 until acne disappears

        // this.shadowGen.useContactHardeningShadowMap = true;
        // this.shadowGen.contactHardeningLightSizeUVRatio = 0.1;
        // this.shadowGen.contactHardeningDarkeningLightSizeUVRatio = 0.3;
        //
        this.shadowGen.setDarkness(0.4);

        this.dirLight2 = new DirectionalLight(
            "shadowLight2",
            new Vector3(0, 0, 0),
            this.scene
        );
        this.dirLight2.position = coordinatesToBabylon([1, -1, 10]);
        this.dirLight2.direction = coordinatesToBabylon([1, -1, -1]);
        this.dirLight2.intensity = 0.4;


        // this.dirLight2.shadowEnabled = true;
        //
        // this.shadowGen2 = new ShadowGenerator(1024, this.dirLight2);
        // this.scene.shadowGenerator2 = this.shadowGen2;
        // this.shadowGen2.useExponentialShadowMap = true;
        // this.shadowGen2.depthScale = 200;                       // default is 50 — try 100–200
        //
        // this.shadowGen2.useContactHardeningShadowMap = true;
        // this.shadowGen2.contactHardeningLightSizeUVRatio = 0.1;
        // this.shadowGen2.contactHardeningDarkeningLightSizeUVRatio = 0.3;
        // this.shadowGen2.setDarkness(0);

        // — BACKGROUND —
        this.scene.clearColor = getBabylonColor(this.config.background_color);

        this.scene.ambientColor = getBabylonColor3(this.config.ambient_color);

        if (this.config.scene.add_fog) {
            if (this.config.scene.fog_mode === 'exp2') {
                this.scene.fogMode = BabylonScene.FOGMODE_EXP2;
            } else if (this.config.scene.fog_mode === 'linear') {
                this.scene.fogMode = BabylonScene.FOGMODE_LINEAR;
            } else if (this.config.scene.fog_mode === 'exp') {
                this.scene.fogMode = BabylonScene.FOGMODE_EXP;
            } else {
                console.warn(`Unknown fog mode: ${this.config.scene.fog_mode}`);
            }
            this.scene.fogDensity = this.config.scene.fog_density;
            this.scene.fogColor = getBabylonColor3(this.config.scene.fog_color);
        }


        // — COORDINATES +
        if (this.config.show_coordinate_system) {
            drawCoordinateSystem(this.scene, this.config.coordinate_system_length);
        }

        // once, after scene creation:
        this.scene.setRenderingOrder(
            0,
            null, // opaque
            null, // alphaTest
            // transparent compare
            (a, b) => {
                const cam = this.scene.activeCamera;
                const da = Vector3.Distance(cam.position, a.getBoundingInfo().boundingSphere.centerWorld);
                const db = Vector3.Distance(cam.position, b.getBoundingInfo().boundingSphere.centerWorld);
                // draw far first, near last (so near blends over far)
                return db - da;
            }
        );

        // const engine = this.scene.getEngine();
        // console.log(engine);
        //
        // engine.runRenderLoop(() => {
        //     // Skip if the canvas has zero size (prevents GL_INVALID_FRAMEBUFFER warnings)
        //     if (!engine.getRenderWidth(true) || !engine.getRenderHeight(true)) return;
        //     this.scene.render();
        // });

        return this.scene;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _addSceneClickListener() {
        this.scene.onPointerObservable.add((pointerInfo) => {
            if (pointerInfo.type === PointerEventTypes.POINTERDOWN) {
                this._handleSingleSceneClick();

            } else if (pointerInfo.type === PointerEventTypes.POINTERDOUBLETAP) {
                this._handleDoubleSceneClick();
            }
        });
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _handleSingleSceneClick() {
        const pick = this.scene.pick(this.scene.pointerX, this.scene.pointerY);
        if (pick.hit) {
            if (pick.pickedMesh.metadata) {
                for (const obj of Object.values(this.objects)) {
                    obj.highlight(false);
                }
                pick.pickedMesh.metadata.object.highlight(true);

                // const center = pick.pickedMesh.getBoundingInfo()
                //     .boundingBox
                //     .centerWorld;
                //
                // // point the camera at that position
                // this.camera.setTarget(center);


                // this.framing.zoomOnMesh(pick.pickedMesh, /* focusXZ=*/ true, () => {
                //     console.log("framing animation done");
                // });


            } else {
                console.log("No object metadata");
            }
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _handleDoubleSceneClick() {
        for (const obj of Object.values(this.objects)) {
            obj.highlight(false);
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _onObjectEvent(obj, event) {
        this.log(`Object ${obj.id} event: ${event}`);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _onObjectLog(obj, message, level = 'info') {
        this.log(`Object ${obj.id}: ${message}`, level);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _onObjectSendMessage(obj, message) {
        this.log(`Object ${obj.id} send message: ${message}`);
    }

    /* -------------------------------------------------------------------------------------------------------------- */

    /* -------------------------------------------------------------------------------------------------------------- */

    /* -------------------------------------------------------------------------------------------------------------- */
    addTestObjects() {


        // const as1 = new ArucoStatic('static1', this, {});
        // this.addObject(as1);


        // this.frodo2 = new BabylonFrodo('frodo2', this, {scaling: 1, color: [0, 0.7, 0.2]});
        // this.frodo2.onLoaded().then(() => {
        //     this.frodo2.setState(0, -1, 0);
        // })

        // const simplebox2 = new BabylonBox('box1', this, {config: {size: {x: 0.1, y: 0.1, z: 0.1}}});
        // // simplebox.onLoaded().then(() => {
        // simplebox2.setPosition([1, 0, 0]);

        return;


        const cir2 = new BabylonCircleDrawing("circle2", this.scene, {
            data: {
                radius: 0.75
            },
            config: {
                circleFillColor: [0, 1, 0, 0.05],
                circleBorderColor: [0, 1, 0, 0.2],
                circleBorderWidth: 0.01,
            }
        });
        this.addObject(cir2);
        cir2.setPosition([0, 0, 0]);

        // // Make a function that changes the size of the circle with an interval. Make it grow and then shrink
        // const changeSize = () => {
        //     const size = cir2.config.radius;
        //     cir2.setRadius(size + 0.01);
        // }
        //
        // setInterval(changeSize, 50);
        // //
        // const line = new BabylonLineDrawing("line1", this.scene, {
        //     config: {
        //         start: [0, 0, 0],
        //         end: [-0.6, -0.2, 0],
        //         lineColor: [1, 0, 0, 0.5],
        //         lineWidth: 0.005,
        //         lineStyle: "dotted",
        //     }
        // });
        // this.addObject(line);
        //
        // const move_line = () => {
        //     const new_end = [Math.sin(Date.now() / 1000), Math.cos(Date.now() / 1000), 0];
        //
        //     line.updatePoints({end: new_end});
        // }
        //
        // setInterval(move_line, 50);

        const simple_bilbo1 = new BabylonBilbo('sb1', this.scene, {});

        simple_bilbo1.onLoaded().then(() => {
            simple_bilbo1.setState(0.5, 0.5, 0, -Math.PI / 4);
        })

        const simple_bilbo2 = new BabylonBilbo('sb1', this.scene, {});

        simple_bilbo2.onLoaded().then(() => {
            simple_bilbo2.setState(0.5, 0.1, 0, -Math.PI / 4);
        })

        const simplebox = new BabylonBox('box1', this.scene, {config: {size: {x: 0.1, y: 0.1, z: 0.1}}});
        // simplebox.onLoaded().then(() => {
        simplebox.setPosition([1, 0, 0]);
        // })

        // // this.addObject(simple_bilbo1);
        // //
        // // this.bilbo2 = new BabylonBilboRealistic('bilbo2', this.scene, {config: {text: '2', color: [0.5, 0.5, 0.7]}});
        //
        // this.frodo1 = new BabylonFrodo('frodo1', this.scene, {config: {scaling: 1}});
        //
        // this.frodo1.onLoaded().then(() => {
        //     this.frodo1.setState(0, 1, -Math.PI / 4);
        // })
        //
        // return;

        // this.frodo2 = new BabylonFrodo('frodo2', this.scene, {scaling: 1, color: [0, 0.7, 0.2]});
        // this.frodo2.onLoaded().then(() => {
        //     this.frodo2.setState(0, -1, 0);
        // })

    }


    dispose() {
        this._resizeObserver?.disconnect();
        this._resizeObserver = null;
        this._mq?.removeEventListener?.('change', this._mqHandler);
        this._mq = this._mqHandler = null;
        window.visualViewport?.removeEventListener?.('resize', this._vvHandler);
        window.removeEventListener('resize', this._winResizeHandler);
        // engine.dispose() etc. if appropriate
    }
}


// =====================================================================================================================
class CameraButton
    extends ButtonWidget {
    constructor(id, config = {}) {
        // Keep the ButtonWidget constructor behavior (it builds the element and calls configureElement)
        super(id, config);

        // Provide a couple of gentle defaults if caller didn't pass them
        const cameraDefaults = {
            image: './icons/camera-icon.png',
            image_width: '75%',
            image_height: '75%',
            number: 1,           // badge number
            adjust_icon_size: true
        };
        this.configuration = {...cameraDefaults, ...this.configuration};

        // Reconfigure again so our defaults take effect when constructed with minimal config
        this.configureElement(this.element);

    }

    configureElement(element) {
        // Build the base button first
        super.configureElement(element);

        // Ensure the button is a positioned container for the badge
        element.style.position = element.style.position || 'relative';

        // Create (or re-attach) the badge
        const number = (this.configuration && this.configuration.number != null)
            ? String(this.configuration.number) : "";

        if (!this._badgeEl) {
            this._badgeEl = document.createElement('div');
            this._badgeEl.className = 'cameraBadge';
        }
        this._badgeEl.textContent = number;

        // Minimal inline styles so you don't need extra CSS
        Object.assign(this._badgeEl.style, {
            position: 'absolute',
            left: '1px',
            bottom: '1px',
            minWidth: '18px',
            height: '18px',
            padding: '0 4px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderRadius: '9px',
            background: 'rgba(0,0,0,1)',
            color: '#fff',
            fontSize: '10px',
            lineHeight: '18px',
            border: '1px solid rgba(255,255,255,0.25)',
            pointerEvents: 'none', // never block clicks on the button
            zIndex: '1',
            opacity: '1',
        });

        // ButtonWidget.configureElement() resets innerHTML every time, so always append (or re-append) the badge last.
        element.appendChild(this._badgeEl);
        element.classList.add('camera-button');
    }

    setNumber(n) {
        this.configuration.number = n;
        if (this._badgeEl) this._badgeEl.textContent = String(n);
    }
}

// =====================================================================================================================
class TerminalButton extends ButtonWidget {
    constructor(id, config = {}) {
        // Keep ButtonWidget behavior (builds element + calls configureElement)
        super(id, config);

        // Safe defaults so the button looks just like your existing one
        const defaults = {
            image: './icons/terminal-icon.png',
            image_width: '75%',
            image_height: '75%',
            notifications: 0,             // starting count
            max_display: 99,              // 100+ shows as "99+"
        };
        this.configuration = {...defaults, ...this.configuration};

        // Internal state
        this._notifCount = Number(this.configuration.notifications) || 0;

        // Re-configure so our defaults apply when constructed with minimal config
        this.configureElement(this.element);

        this.container.style.overflow = 'visible';
    }

    configureElement(element) {
        super.configureElement(element);

        element.classList.add('terminal-button');
        element.style.position = element.style.position || 'relative';

        // ⬇️ This is the important part: beat the generic .buttonItem { overflow:hidden }
        element.style.overflow = 'visible';
        element.style.zIndex = '1'; // keep the badge above neighbors

        if (!this._badgeEl) {
            this._badgeEl = document.createElement('div');
            this._badgeEl.className = 'terminalBadge';
        }

        this._renderBadge();
        element.appendChild(this._badgeEl);
    }

    // --- Public API -------------------------------------------------------------------------------------------------
    increaseNotificationCount(delta = 1) {
        const d = Number.isFinite(delta) ? delta : 1;
        this.setNotificationCount((this._notifCount || 0) + d);
    }

    removeNotificationCount() {
        // Resets to zero (and hides the badge)
        this.setNotificationCount(0);
    }

    setNotificationCount(n) {
        const next = Math.max(0, Number(n) || 0);
        if (next === this._notifCount) return;
        this._notifCount = next;
        this._renderBadge();
    }

    getNotificationCount() {
        return this._notifCount || 0;
    }

    // --- Private helpers -------------------------------------------------------------------------------------------
    _renderBadge() {
        if (!this._badgeEl) return;

        const count = this._notifCount || 0;
        if (count <= 0) {
            this._badgeEl.style.display = 'none';
            return;
        }

        const cap = Number(this.configuration.max_display) || 99;
        const text = count > cap ? `${cap}+` : String(count);

        this._badgeEl.textContent = text;
        this._badgeEl.style.display = 'flex';
    }
}

// =====================================================================================================================
class RecordButton extends ButtonWidget {
    constructor(id, config = {}) {
        super(id, config);

        // Gentle defaults
        const defaults = {
            image: './icons/record-icon.png',
            image_width: '85%',
            image_height: '85%',
            tooltip: 'Record'
        };
        this.configuration = {...defaults, ...this.configuration};

        // Callbacks used by the context menu entries
        this.callbacks.add('hbr_recording');
        this.callbacks.add('hbr_recording_overlay');

        // Internal timer state
        this._recStartTs = 0;
        this._ticker = null;
        this._timerEl = null;

        // Build DOM + styles
        this.configureElement(this.element);

        // Context menu: High Bit Rate
        const high_bit_rate_element = new ContextMenuItem('hbr', {
            name: 'Record High Bit Rate',
            front_icon: '🔴'
        });
        this.addItemToContextMenu(high_bit_rate_element);
        high_bit_rate_element.callbacks.get('click').register(() => {
            this.callbacks.get('hbr_recording').call();
        });

        // Context menu: High Bit Rate with Overlay
        const high_bit_rate_element2 = new ContextMenuItem('hbr2', {
            name: "Record High Bit Rate with Overlay",
            front_icon: '🔴'
        });
        this.addItemToContextMenu(high_bit_rate_element2);
        high_bit_rate_element2.callbacks.get('click').register(() => {
            this.callbacks.get('hbr_recording_overlay').call();
        });


    }

    configureElement(element) {
        super.configureElement(element);
        element.classList.add('record-button');

        if (this.configuration.tooltip) {
            this.setTooltip(this.configuration.tooltip);
        }

        // The button must be a positioned container so the timer can sit above it
        element.style.position = element.style.position || 'relative';
        element.style.overflow = 'visible';

        // Ensure the small timer pill exists (but hidden until recording)
        if (!this._timerEl) {
            this._timerEl = document.createElement('div');
            this._timerEl.className = 'record-timer';
            this._timerEl.setAttribute('aria-hidden', 'true');
            this._timerEl.textContent = '00:00';
            // this.container.appendChild(this._timerEl);
            element.appendChild(this._timerEl);
        }

        this.container.style.overflow = 'visible';
    }

    /** Turns on the blinking / 'REC' style and shows the mm:ss timer */
    startBlinking() {
        if (!this.element) return;

        // Add visual recording state
        this.element.classList.add('is-recording');
        this.setTooltip('');
        this.element.setAttribute('aria-pressed', 'true');

        // (Re)start timer logic
        this._recStartTs = Date.now();
        if (this._timerEl) this._timerEl.textContent = '00:00';

        // Clear any previous ticker (safety)
        if (this._ticker) {
            clearInterval(this._ticker);
            this._ticker = null;
        }

        // Update every 250ms so we cross second boundaries smoothly, but only show mm:ss
        this._ticker = setInterval(() => {
            if (!this._timerEl) return;
            const elapsedMs = Math.max(0, Date.now() - this._recStartTs);
            const totalSeconds = Math.floor(elapsedMs / 1000);
            const mm = String(Math.floor(totalSeconds / 60)).padStart(2, '0');
            const ss = String(totalSeconds % 60).padStart(2, '0');
            this._timerEl.textContent = `${mm}:${ss}`;
        }, 250);
    }

    /** Turns off the blinking / 'REC' style and hides the timer */
    stopBlinking() {
        if (!this.element) return;

        // Visual state off
        this.element.classList.remove('is-recording');
        this.setTooltip(this.configuration.tooltip || 'Record');
        this.element.setAttribute('aria-pressed', 'false');

        // Stop timer + reset text (kept hidden by CSS when not recording)
        if (this._ticker) {
            clearInterval(this._ticker);
            this._ticker = null;
        }
        if (this._timerEl) {
            this._timerEl.textContent = '00:00';
        }
    }

    /** Convenience for toggling from the outside */
    setRecording(isRecording) {
        if (isRecording) this.startBlinking();
        else this.stopBlinking();
    }
}

// =====================================================================================================================
export class BabylonContainer {

    /** @type {HTMLElement | null } */
    container = null;

    /** @type {HTMLElement | null } */
    element = null;

    /** @type {Callbacks} */
    callbacks


    /** @type {Object} */
    cameras = {}

    // TODO: This belong to the debug overlay
    /** @type {number} */
    _suppressClickUntil = 0;


    // === CONSTRUCTOR =================================================================================================
    constructor(id, container, payload = {}) {

        const default_config = {
            show_widget_controls: true,
            widget_controls_position: 'inside',  // inside, outside
            control_bar_height: 35, // px
            babylon: {},
            title: 'Dustin Babylon.JS',
        }

        this.configuration = {...default_config, ...payload.config};

        this.container = container;
        this.id = id;

        this.element = this.initializeElement();
        this.configureElement();

        this.babylon = new Babylon(this.id, this.babylon_canvas, payload.config, payload.objects);

        this.babylon_canvas.setAttribute('tabindex', '-1');
        this.babylon_canvas.addEventListener('mousedown', (e) => e.preventDefault(), {capture: true});

        this._attachBabylonCallbacks();
        this.attachListeners();

        this._debugCollapse = {};
        this._debugBuilt = false;


        this.top_bar_time = this.top_bar_time || this.element.querySelector('.top-bar .time');

        // --- simple elapsed timer ---
        this._timerStart = Date.now();

        const pad2 = (n) => String(n).padStart(2, '0');
        const tickElapsed = () => {
            const secs = Math.floor((Date.now() - this._timerStart) / 1000);
            const h = Math.floor(secs / 3600);
            const m = Math.floor((secs % 3600) / 60);
            const s = secs % 60;
            if (this.top_bar_time) this.top_bar_time.textContent = `${pad2(h)}:${pad2(m)}:${pad2(s)}`;
        };

        // kick it off + repeat every second
        tickElapsed();
        this._timeInterval = setInterval(tickElapsed, 1000);
    }

    // === METHODS =====================================================================================================
    initializeElement() {
        const element = document.createElement('div');
        element.classList.add('babylon-container');

        // const el = document.querySelector('.no-focus-on-click');
        // element.addEventListener('mousedown', e => e.preventDefault()); // stops focus

        if (this.configuration.widget_controls_position === 'inside') {
            element.classList.add('babylon-controls-inside');
        } else {
            element.classList.add('babylon-controls-outside');
        }


        this.babylon_canvas_container = document.createElement('div');
        this.babylon_canvas_container.classList.add('babylon-canvas-container');
        element.appendChild(this.babylon_canvas_container);

        this.babylon_canvas = document.createElement('canvas');
        this.babylon_canvas.classList.add('babylon-canvas');
        this.babylon_canvas_container.appendChild(this.babylon_canvas);

        this.babylon_controls = document.createElement('div');
        this.babylon_controls.classList.add('babylon-controls');
        element.appendChild(this.babylon_controls);
        this.babylon_controls.style.setProperty('--control-height', `${this.configuration.control_bar_height}px`)


        // Connection Indicator
        this.connection_indicator = document.createElement('div');
        this.connection_indicator.classList.add('connection');
        this.babylon_controls.appendChild(this.connection_indicator);

        this.connection_circle = document.createElement('div');
        this.connection_circle.classList.add('connection-circle');
        this.connection_indicator.appendChild(this.connection_circle);

        this.connection_message = document.createElement('div');
        this.connection_message.classList.add('connection-messages');
        this.connection_indicator.appendChild(this.connection_message);

        this.connection_message.textContent = '20 M/s'

        // Add buttons here
        const button_container = document.createElement('div');
        button_container.classList.add('buttons');
        this.babylon_controls.appendChild(button_container);

        const buttons = {}

        this.button_record = new RecordButton('record', {
            config: {image: './icons/record-icon.png', image_width: '85%', image_height: '85%'}
        });
        this.button_record.setTooltip("Record");
        this.button_record.attach(button_container);

        this.button_record.callbacks.get('click').register(() => {
            if (!this.babylon.is_recording) {
                this.babylon.startRecording("babylonjs.webm",);
            } else {
                this.babylon.stopRecording();
            }
        });

        this.button_record.callbacks.get('hbr_recording').register(() => {
            if (!this.babylon.is_recording) {
                this.babylon.startRecordingHiBitrate();
            }
        });

        this.button_record.callbacks.get('hbr_recording_overlay').register(() => {
            if (!this.babylon.is_recording) {
                // this.babylon.startRecordingHiBitrate("babylonjs.webm");
                this.startRecordingHiBitrateWithOverlay();
            }
        });

        const button_settings = new ButtonWidget('settings',
            {
                config: {
                    image: './icons/settings-icon.png',
                    image_width: '75%',
                    image_height: '75%',
                }
            });

        button_settings.setTooltip("Settings");
        button_settings.attach(button_container);

        const button_assets = new ButtonWidget('assets',
            {
                config: {
                    image: './icons/assets-icon.png',
                    image_width: '75%',
                    image_height: '75%',
                }
            });

        button_assets.setTooltip("Assets");
        button_assets.attach(button_container);

        const button_fullscreen = new ButtonWidget('fullscreen',
            {
                config: {
                    image: './icons/fullscreen-icon.png',
                    image_width: '75%',
                    image_height: '75%',
                }
            })

        button_fullscreen.setTooltip("Fullscreen");
        button_fullscreen.attach(button_container);

        this.button_terminal = new TerminalButton('terminal', {
            config: {image: './icons/terminal-icon.png'}
        });

        this.button_terminal.setTooltip("Terminal");
        this.button_terminal.attach(button_container);

        const button_debug = new ButtonWidget('terminal',
            {
                config: {
                    image: './icons/debug-icon.png',
                    image_width: '75%',
                    image_height: '75%',
                }
            })

        button_debug.setTooltip("Debug");
        button_debug.attach(button_container);

        button_debug.callbacks.get('click').register(() => {
            if (this.debug_overlay.style.display === 'flex') {
                this.closeDebugOverlay();
            } else {
                this.openDebugOverlay();
            }
        })

        const top_bar = document.createElement('div');
        top_bar.classList.add('top-bar');
        element.appendChild(top_bar);

        const top_bar_title = document.createElement('div');
        top_bar_title.classList.add('title');
        top_bar_title.textContent = this.configuration.title;
        top_bar.appendChild(top_bar_title);

        const top_bar_time = document.createElement('div');
        top_bar_time.classList.add('time');
        top_bar_time.textContent = "00:00:00";
        top_bar.appendChild(top_bar_time);


        // Overlays
        this.terminal_overlay = document.createElement('div');
        this.terminal_overlay.classList.add('terminal-overlay');
        this.terminal_overlay.style.display = 'none';

        this.button_terminal.callbacks.get('click').register(() => {
            if (this.terminal_overlay.style.display === 'flex') {
                this.closeTerminalOverlay();
            } else {
                this.openTerminalOverlay();
            }
        })

        this.terminal_output = new LineScrollTextWidget('terminal_output', {
            config: {
                font_size: 10,
            }
        });
        this.terminal_overlay.appendChild(this.terminal_output.getElement());
        const terminal_close_button_container = document.createElement('div');
        terminal_close_button_container.classList.add('terminal-close-button-container');
        this.terminal_overlay.appendChild(terminal_close_button_container);
        this.terminal_close_button = new ButtonWidget('terminal_close', {
            config:
                {
                    icon: "❌"
                }
        });
        this.terminal_close_button.callbacks.get('click').register(() => {
            this.closeTerminalOverlay();
        })
        terminal_close_button_container.appendChild(this.terminal_close_button.getElement());

        this.terminal_output.addLine("Welcome to Dustin's Babylon.js container!");
        element.appendChild(this.terminal_overlay);


        // Babylon Debug Overlay
        this.debug_overlay = document.createElement('div');
        this.debug_overlay.classList.add('debug-overlay');
        this.debug_overlay.style.display = 'none';
        element.appendChild(this.debug_overlay);


        this.top_bar = top_bar;
        this.top_bar_title = top_bar_title;
        this.top_bar_time = top_bar_time;

        this._setConnectionStatus(false, '');

        this.container.appendChild(element);
        return element;
    }

    // -----------------------------------------------------------------------------------------------------------------
    configureElement() {

    }

    // -----------------------------------------------------------------------------------------------------------------
    attachListeners() {

    }

    // -----------------------------------------------------------------------------------------------------------------
    addLineToTerminal(line, color = 'white', add_notification = true) {

        this.terminal_output.addLine(line, color);
        if (add_notification) {
            if (this.terminal_overlay.style.display === 'none') {
                this.button_terminal.increaseNotificationCount();
            }
        }
    }

    // -----------------------------------------------------------------------------------------------------------------
    openTerminalOverlay() {
        this.closeDebugOverlay();
        const controlsHeight = this.babylon_controls.offsetHeight;
        const topBarHeight = this.element.querySelector('.top-bar').offsetHeight;

        this.terminal_overlay.style.top = `${topBarHeight + 5}px`;
        this.terminal_overlay.style.bottom = `${controlsHeight + 5}px`;


        this.terminal_overlay.style.display = 'flex';

        this.terminal_output.scrollDown();
        this.button_terminal.setNotificationCount(0);

    }

    // -----------------------------------------------------------------------------------------------------------------
    closeTerminalOverlay() {
        this.terminal_overlay.style.display = 'none';

    }

    // -----------------------------------------------------------------------------------------------------------------
    addCameraView(camera_data = {}) {
        // Where to append: the existing control bar's .buttons grid
        const buttonContainer = this.babylon_controls.querySelector('.buttons');
        if (!buttonContainer) {
            console.warn('BabylonContainer.addCameraView: .buttons container not found');
            return;
        }

        // Decide id and sequential number
        const currentCount = Object.keys(this.cameras).length;
        const number = (camera_data.number != null) ? camera_data.number : (currentCount + 1);
        const id = camera_data.id || `camera_${number}`;

        // Create the button
        const btn = new CameraButton(id, {
            config: {
                image: camera_data.image || "./icons/camera-icon.png",
                image_width: "75%",
                image_height: "75%",
                text: (camera_data.text || ""), // optional label if you later want one
                number
            }
        });

        // Keep a reference
        this.cameras[id] = {button: btn, data: camera_data};

        // Add to the grid
        btn.attach(buttonContainer);
        btn.setTooltip(camera_data.name || `Camera ${number}`);


        btn.callbacks.get('click').register(() => {
            this.babylon.setArcRotateCamera(camera_data.position,
                camera_data.target,
                camera_data.alpha,
                camera_data.beta,
                camera_data.radius);
        })

        // Auto-adjust the grid columns to fit however many buttons exist now
        const totalButtons = buttonContainer.children.length;
        buttonContainer.style.gridTemplateColumns = `repeat(${totalButtons}, 1fr)`;
        buttonContainer.style.aspectRatio = `${totalButtons}`;
    }


    // -----------------------------------------------------------------------------------------------------------------
    startRecordingHiBitrateWithOverlay({
                                           fileName = "babylonjs.webm",
                                           fps = 60,
                                           videoBitsPerSecond = 12_000_000,
                                           enableTimeTicker = false,      // if true, updates this.top_bar_time every second while recording
                                       } = {}) {
        const engine = this.babylon.scene?.getEngine?.();
        const src = engine?.getRenderingCanvas?.();

        if (!engine || !src) {
            this.babylon?.log?.("No canvas for recording.", "error");
            return;
        }
        if (this.babylon.is_recording) {
            this.babylon?.log?.("Already recording.", "warning");
            return;
        }

        // -------- helpers ----------
        const syncSize = () => {
            mix.width = src.width;
            mix.height = src.height;
        };

        // Rounded-rect path helper (single radius)
        const roundRectPath = (ctx, x, y, w, h, r) => {
            const rr = Math.max(0, Math.min(r, Math.min(w, h) / 2));
            ctx.beginPath();
            ctx.moveTo(x + rr, y);
            ctx.arcTo(x + w, y, x + w, y + h, rr);
            ctx.arcTo(x + w, y + h, x, y + h, rr);
            ctx.arcTo(x, y + h, x, y, rr);
            ctx.arcTo(x, y, x + w, y, rr);
            ctx.closePath();
        };

        // Minimal parser for the FIRST box-shadow only (ignores "inset" and spread)
        const parseBoxShadow = (sh) => {
            if (!sh || sh === "none") return null;
            const m = sh.match(/(-?\d+(?:\.\d+)?)px\s+(-?\d+(?:\.\d+)?)px(?:\s+(\d+(?:\.\d+)?)px)?(?:\s+\d+(?:\.\d+)?)?\s+(.*)/);
            if (!m) return null;
            const [, ox, oy, blur = "0", color = "rgba(0,0,0,0.25)"] = m;
            return {ox: +ox, oy: +oy, blur: +blur, color: color.trim()};
        };

        // Optional ticking of the time element while recording
        let ticking = false, tickTimer = null;
        const startTick = () => {
            if (!enableTimeTicker || ticking) return;
            ticking = true;
            tickTimer = setInterval(() => {
                if (this.top_bar_time) {
                    this.top_bar_time.textContent = new Date().toLocaleTimeString();
                }
            }, 1000);
        };
        const stopTick = () => {
            ticking = false;
            if (tickTimer) clearInterval(tickTimer), (tickTimer = null);
        };

        // -------- set higher internal resolution while recording ----------
        this.babylon._prevScaling = engine.getHardwareScalingLevel?.() ?? 1;
        // halve the scaling level (i.e., render more pixels), but not below 0.25
        engine.setHardwareScalingLevel(Math.max(0.25, this.babylon._prevScaling * 0.5));

        // -------- build mix canvas ----------
        const mix = document.createElement('canvas');
        const ctx = mix.getContext('2d', {alpha: true});
        ctx.imageSmoothingEnabled = true;
        syncSize();

        // -------- per-frame composer ----------
        let rafId = 0;
        const draw = () => {
            if (mix.width !== src.width || mix.height !== src.height) syncSize();

            // CSS pixels -> video pixels; keeps fonts crisp under DPR / scaling
            const rect = src.getBoundingClientRect();
            const cssToVideo = rect.width ? (src.width / rect.width) : (window.devicePixelRatio || 1);

            ctx.clearRect(0, 0, mix.width, mix.height);
            ctx.drawImage(src, 0, 0);

            // draw a "pill" for a DOM element at left or right edge
            const drawPill = (el, anchor = "left") => {
                if (!el) return;

                const s = getComputedStyle(el);
                if (s.display === "none" || s.visibility === "hidden" || (parseFloat(s.opacity) || 1) === 0) return;

                const text = el.textContent ?? "";

                // font
                const fontPx = (parseFloat(s.fontSize) || 16) * cssToVideo;
                const font = `${s.fontStyle || ""} ${s.fontVariant || ""} ${s.fontWeight || 400} ${fontPx}px ${s.fontFamily || "sans-serif"}`.trim();
                ctx.font = font;
                ctx.textBaseline = "top";

                // paddings
                const padL = (parseFloat(s.paddingLeft) || 12) * cssToVideo;
                const padR = (parseFloat(s.paddingRight) || 12) * cssToVideo;
                const padT = (parseFloat(s.paddingTop) || 6) * cssToVideo;
                const padB = (parseFloat(s.paddingBottom) || 6) * cssToVideo;

                // text metrics
                const m = ctx.measureText(text);
                const tW = m.width;
                const tH = (m.actualBoundingBoxAscent || fontPx * 0.8) + (m.actualBoundingBoxDescent || fontPx * 0.2);

                // box size + position
                const boxW = tW + padL + padR;
                const boxH = tH + padT + padB;

                const inset = 16 * cssToVideo;
                let x = inset, y = inset;
                if (anchor === "right") x = mix.width - inset - boxW;

                // styles
                const bg = (s.backgroundColor && s.backgroundColor !== "rgba(0, 0, 0, 0)")
                    ? s.backgroundColor
                    : "rgba(0,0,0,0.55)";
                const color = s.color || "#fff";
                const radius = ((parseFloat(s.borderTopLeftRadius) || parseFloat(s.borderRadius) || (boxH / 2))) * cssToVideo;
                const bw = (parseFloat(s.borderWidth) || 0) * cssToVideo;
                const bc = s.borderColor || "transparent";
                const bs = parseBoxShadow(s.boxShadow);

                // background + shadow
                ctx.save();
                if (bs) {
                    ctx.shadowColor = bs.color;
                    ctx.shadowBlur = bs.blur * cssToVideo;
                    ctx.shadowOffsetX = bs.ox * cssToVideo;
                    ctx.shadowOffsetY = bs.oy * cssToVideo;
                } else {
                    ctx.shadowColor = "transparent";
                }
                ctx.globalAlpha = 0.8;

                roundRectPath(ctx, x, y, boxW, boxH, radius);
                ctx.fillStyle = bg;
                ctx.fill();

                if (bw > 0) {
                    ctx.lineWidth = bw;
                    ctx.strokeStyle = bc;
                    ctx.stroke();
                }

                // text (no shadow for crisp glyphs)
                ctx.shadowColor = "transparent";
                ctx.fillStyle = color;
                ctx.fillText(text, x + padL, y + padT);
                ctx.restore();
            };

            // LEFT: title, RIGHT: time — read LIVE every frame
            drawPill(this.top_bar_title, "left");
            drawPill(this.top_bar_time, "right");

            rafId = requestAnimationFrame(draw);
        };
        rafId = requestAnimationFrame(draw);

        // -------- start recording the mix canvas ----------
        const mime = _chooseBestMime();
        const stream = mix.captureStream(fps);
        const rec = new MediaRecorder(stream, {mimeType: mime, videoBitsPerSecond});

        // Hook into your existing stop flow
        this.babylon._customRecorder = rec;
        this.babylon.is_recording = true;

        const chunks = [];
        rec.ondataavailable = (e) => {
            if (e.data?.size) chunks.push(e.data);
        };

        rec.onstop = () => {
            cancelAnimationFrame(rafId);
            stopTick();

            const blob = new Blob(chunks, {type: mime});
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = fileName;
            a.click();
            setTimeout(() => URL.revokeObjectURL(a.href), 5000);

            try {
                engine.setHardwareScalingLevel(this.babylon._prevScaling);
                this.babylon.log("Setting back hardware scaling", "important");
            } catch {
            }

            this.babylon._customRecorder = null;
            this.babylon.is_recording = false;
            this.babylon.log(`High-bitrate recording saved (${Math.round(blob.size / 1024)} KB).`, "important");
            this.babylon.callbacks.get('record_stop').call();
        };

        rec.start(1000); // collect data every second
        this.babylon.log(`Started high-bitrate recording with HUD (fps=${fps}, ~${Math.round(videoBitsPerSecond / 1e6)} Mbps, ${mime}).`, "important");
        this.babylon.callbacks.get('record_start').call(fileName);

        // Start optional ticking of the time label
        startTick();
    }

    /* === PRIVATE METHODS ========================================================================================== */
    _onBabylonLog(message, level = 'info') {
        switch (level) {
            case 'debug':
                this.addLineToTerminal(message, 'white', false);
                break;
            case 'info':
                this.addLineToTerminal(message, 'white', false);
                break;
            case 'warning':
                this.addLineToTerminal(message, 'orange', true);
                break;
            case 'error':
                this.addLineToTerminal(message, 'red', true);
                break;
            case 'important':
                this.addLineToTerminal(message, 'green', true);
                break;
            default:
                console.warn(`BabylonContainer._onBabylonLog: unknown log level: ${level}`);
                break;
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _attachBabylonCallbacks() {
        this.babylon.callbacks.get('log').register(this._onBabylonLog.bind(this));
        this.babylon.callbacks.get('record_start').register(() => {
            this.button_record.startBlinking();
        });
        this.babylon.callbacks.get('record_stop').register(() => {
            this.button_record.stopBlinking();
        })

        this.babylon.callbacks.get('websocket_connected').register(() => {
            this._setConnectionStatus(true, this.babylon.getMessagesPerSecond());
            if (this._mpsTimer) clearInterval(this._mpsTimer);
            this._mpsTimer = setInterval(() => {
                this._setConnectionStatus(true, this.babylon.getMessagesPerSecond());
            }, 1000);
        });
        this.babylon.callbacks.get('websocket_disconnected').register(() => {
            if (this._mpsTimer) clearInterval(this._mpsTimer), this._mpsTimer = null;
            this._setConnectionStatus(false, '');
        });

        this.babylon.callbacks.get('initialized').register(this._on_babylon_initialized.bind(this))
    }

    _on_babylon_initialized() {
        this.addCameraView({
            name: 'default',
            position: coordinatesFromBabylon(this.babylon.camera.position),
            target: coordinatesFromBabylon(this.babylon.camera.target),
            alpha: this.babylon.camera.alpha,
            beta: this.babylon.camera.beta,
            radius: this.babylon.camera.radius,
        })

        this.addCameraView({
            name: 'top',
            position: [0, 0, 6],
            target: [0, 0, 0],
            alpha: deg2rad(90),
            beta: 0,
            radius: 6
        });
    }

    _setConnectionStatus(connected, messages_per_second) {
        if (connected) {
            this.connection_circle.style.backgroundColor = getColor([154 / 255, 205 / 255, 50 / 255]);
            this.connection_message.style.display = 'block';
            this.connection_message.textContent = `${messages_per_second} msg/s`;
        } else {
            this.connection_circle.style.backgroundColor = getColor([255 / 255, 64 / 255, 64 / 255]);
            this.connection_message.textContent = ``;
            this.connection_message.style.display = 'none';
        }


    }

    /* +++ DEBUG OVERLAY ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++ */
    _ensureDebugOverlayScaffold() {
        if (this._debugBuilt) return;

        // Panel that holds the content (we'll scroll this programmatically)
        this._debugPanel = document.createElement('div');
        this._debugPanel.classList.add('debug-panel');
        // Important: we will NOT enable pointer events on this element, so canvas interactions pass through.
        // Scrolling is handled by a global wheel interceptor.
        this.debug_overlay.appendChild(this._debugPanel);
        this._debugBuilt = true;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _formatNum(n, digits = 3) {
        if (n == null || Number.isNaN(n)) return '—';
        return Number(n).toFixed(digits);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _formatVec3(v) {
        if (!v) return '—';
        return `(${this._formatNum(v[0])}, ${this._formatNum(v[1])}, ${this._formatNum(v[2])})`;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _buildCategory(parent, name, buildBody) {
        const collapsed = !!this._debugCollapse[name];

        const cat = document.createElement('div');
        cat.className = 'debug-category' + (collapsed ? ' collapsed' : '');
        cat.dataset.name = name;

        // Header (visually clickable, but the panel itself is pointer-events:none;
        // we toggle via a global capture-phase click interceptor)
        const title = document.createElement('button');
        title.type = 'button';
        title.className = 'debug-category-title';
        title.innerHTML = `
        <span class="caret" aria-hidden="true"></span>
        <span class="title-text">${name}</span>
    `;

        const body = document.createElement('div');
        body.className = 'debug-body';

        buildBody(body);

        cat.appendChild(title);
        cat.appendChild(body);
        parent.appendChild(cat);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _renderDebugOverlay(debugData) {
        if (!this._debugPanel) return;

        const root = document.createElement('div');
        root.className = 'debug-root';

        // ===== Camera =====
        const cam = debugData?.camera || {present: false};

        this._buildCategory(root, 'Camera', (body) => {
            const addField = (label, value, indent = false) => {
                const row = document.createElement('div');
                row.className = 'debug-field' + (indent ? ' indent' : '');
                const l = document.createElement('span');
                l.className = 'debug-label';
                l.textContent = label;
                const v = document.createElement('span');
                v.className = 'debug-value';
                v.textContent = value;
                row.appendChild(l);
                row.appendChild(v);
                body.appendChild(row);
            };

            if (!cam.present) {
                addField('Present', 'No active camera');
                return;
            }

            addField('Type', cam.type || '—');
            addField('Name', cam.name ?? '—');
            addField('Mode', cam.mode ?? '—');
            addField('FOV (deg)', this._formatNum(cam.fov_deg));
            addField('MinZ / MaxZ', `${this._formatNum(cam.minZ)} / ${this._formatNum(cam.maxZ)}`);
            addField('Position', this._formatVec3(cam.position));
            if (cam.target) addField('Target', this._formatVec3(cam.target));
            if (cam.rotation_euler_deg) {
                const [rx, ry, rz] = cam.rotation_euler_deg;
                addField('Rotation (deg)', `(${this._formatNum(rx)}, ${this._formatNum(ry)}, ${this._formatNum(rz)})`);
            }
            if (cam.upVector) addField('Up Vector', this._formatVec3(cam.upVector));
            addField('Inertia', this._formatNum(cam.inertia));

            if (cam.arcRotate) {
                addField('— ArcRotate —', '', false);
                addField('alpha (deg)', this._formatNum(cam.arcRotate.alpha_deg), true);
                addField('beta (deg)', this._formatNum(cam.arcRotate.beta_deg), true);
                addField('radius', this._formatNum(cam.arcRotate.radius), true);
                addField('α limits (deg)',
                    `${this._formatNum(cam.arcRotate.lowerAlphaLimit_deg)} / ${this._formatNum(cam.arcRotate.upperAlphaLimit_deg)}`, true);
                addField('β limits (deg)',
                    `${this._formatNum(cam.arcRotate.lowerBetaLimit_deg)} / ${this._formatNum(cam.arcRotate.upperBetaLimit_deg)}`, true);
                addField('radius limits',
                    `${this._formatNum(cam.arcRotate.lowerRadiusLimit)} / ${this._formatNum(cam.arcRotate.upperRadiusLimit)}`, true);
                addField('wheelPrecision', this._formatNum(cam.arcRotate.wheelPrecision, 0), true);
                addField('wheelDeltaPercentage', this._formatNum(cam.arcRotate.wheelDeltaPercentage, 4), true);
                addField('panningSensibility', this._formatNum(cam.arcRotate.panningSensibility, 0), true);
                addField('angularSensibilityX / Y',
                    `${this._formatNum(cam.arcRotate.angularSensibilityX, 0)} / ${this._formatNum(cam.arcRotate.angularSensibilityY, 0)}`, true);
                addField('behaviors', [
                    cam.arcRotate.useAutoRotationBehavior ? 'auto' : null,
                    cam.arcRotate.useBouncingBehavior ? 'bounce' : null,
                    cam.arcRotate.useFramingBehavior ? 'framing' : null
                ].filter(Boolean).join(', ') || '—', true);
                addField('inertial α/β/radius',
                    `${this._formatNum(cam.arcRotate.inertialAlphaOffset_deg)} / ${this._formatNum(cam.arcRotate.inertialBetaOffset_deg)} / ${this._formatNum(cam.arcRotate.inertialRadiusOffset)}`, true);
                addField('inertial pan X/Y',
                    `${this._formatNum(cam.arcRotate.inertialPanningX)} / ${this._formatNum(cam.arcRotate.inertialPanningY)}`, true);
            }

            if (cam.follow) {
                addField('— Follow —', '', false);
                addField('lockedTarget', cam.follow.lockedTarget ? 'yes' : 'no', true);
                addField('radius', this._formatNum(cam.follow.radius), true);
                addField('heightOffset', this._formatNum(cam.follow.heightOffset), true);
                addField('rotationOffset (deg)', this._formatNum(cam.follow.rotationOffset_deg), true);
                addField('cameraAcceleration', this._formatNum(cam.follow.cameraAcceleration, 4), true);
                addField('maxCameraSpeed', this._formatNum(cam.follow.maxCameraSpeed, 4), true);
            }

            if (cam.freeLike) {
                const name = (cam.type || '').replace('Camera', '') || 'Free-like';
                addField(`— ${name} —`, '', false);
                addField('speed', this._formatNum(cam.freeLike.speed), true);
                addField('angularSensibility', this._formatNum(cam.freeLike.angularSensibility, 0), true);
                addField('keys Up/Down/Left/Right',
                    `${JSON.stringify(cam.freeLike.keysUp)} / ${JSON.stringify(cam.freeLike.keysDown)} / ${JSON.stringify(cam.freeLike.keysLeft)} / ${JSON.stringify(cam.freeLike.keysRight)}`, true);
                addField('ellipsoid', this._formatVec3(cam.freeLike.ellipsoid), true);
            }
        });

        // Swap content then cache header elements for hit-testing
        this._debugPanel.replaceChildren(root);
        this._debugHeaders = Array.from(this._debugPanel.querySelectorAll('.debug-category-title'));
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _findHeaderAt(x, y) {
        if (!this._debugPanel || !this._debugHeaders || !this._debugHeaders.length) return null;
        for (const h of this._debugHeaders) {
            const r = h.getBoundingClientRect();
            if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) return h;
        }
        return null;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _attachDebugInterceptors() {
        // Wheel: scroll the panel and block Babylon zoom (unchanged)
        if (!this._onDebugWheel) {
            this._onDebugWheel = (e) => {
                if (!this._debugPanel || this.debug_overlay.style.display !== 'flex') return;

                const r = this._debugPanel.getBoundingClientRect();
                const overPanel = (e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom);
                if (!overPanel) return;

                const unit = (e.deltaMode === 1) ? 16 : 1; // Firefox normalization
                this._debugPanel.scrollTop += e.deltaY * unit;
                this._debugPanel.scrollLeft += e.deltaX * unit;

                e.preventDefault();
                e.stopPropagation();
                if (e.stopImmediatePropagation) e.stopImmediatePropagation();
            };
            window.addEventListener('wheel', this._onDebugWheel, {passive: false, capture: true});
        }

        // Toggle on pointerdown ONLY, then fence the click
        if (!this._onDebugPointerDown) {
            this._onDebugPointerDown = (e) => {
                if (!this._debugPanel || this.debug_overlay.style.display !== 'flex') return;

                const header = this._findHeaderAt(e.clientX, e.clientY);
                if (!header) return;

                const cat = header.closest('.debug-category');
                const name = cat?.dataset?.name;
                const isCollapsed = !cat.classList.contains('collapsed');
                cat.classList.toggle('collapsed', isCollapsed);
                if (name) this._debugCollapse[name] = isCollapsed;

                // Fence the follow-up 'click' so it doesn't toggle again
                this._suppressClickUntil = performance.now() + 350;

                e.preventDefault();
                e.stopPropagation();
                if (e.stopImmediatePropagation) e.stopImmediatePropagation();
            };
            window.addEventListener('pointerdown', this._onDebugPointerDown, {capture: true});
        }

        // Swallow the synthetic click right after we handled pointerdown
        if (!this._onDebugClickFence) {
            this._onDebugClickFence = (e) => {
                if (performance.now() < this._suppressClickUntil) {
                    e.preventDefault();
                    e.stopPropagation();
                    if (e.stopImmediatePropagation) e.stopImmediatePropagation();
                }
            };
            window.addEventListener('click', this._onDebugClickFence, {capture: true});
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _detachDebugInterceptors() {
        if (this._onDebugWheel) {
            window.removeEventListener('wheel', this._onDebugWheel, {capture: true});
            this._onDebugWheel = null;
        }
        if (this._onDebugPointerDown) {
            window.removeEventListener('pointerdown', this._onDebugPointerDown, {capture: true});
            this._onDebugPointerDown = null;
        }
        if (this._onDebugClickFence) {
            window.removeEventListener('click', this._onDebugClickFence, {capture: true});
            this._onDebugClickFence = null;
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _startDebugUpdates() {
        if (this._debugInterval) return;
        this._debugInterval = setInterval(() => {
            const data = this.babylon.getDebugData();
            this._renderDebugOverlay(data);
        }, 200);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _stopDebugUpdates() {
        if (this._debugInterval) {
            clearInterval(this._debugInterval);
            this._debugInterval = null;
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    openDebugOverlay() {
        this.closeTerminalOverlay();
        this.debug_overlay.style.display = 'flex';

        const controlsHeight = this.babylon_controls.offsetHeight;
        const topBarHeight = this.element.querySelector('.top-bar').offsetHeight;

        this.debug_overlay.style.top = `${topBarHeight + 5}px`;
        this.debug_overlay.style.bottom = `${controlsHeight + 5}px`;

        this._ensureDebugOverlayScaffold();

        this._renderDebugOverlay(this.babylon.getDebugData());
        this._startDebugUpdates();
        this._attachDebugInterceptors();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    closeDebugOverlay() {
        this._stopDebugUpdates();
        this._detachDebugInterceptors();
        this.debug_overlay.style.display = 'none';
    }

    resize() {

    }

    onFirstShow() {
        this.babylon._addGlobalResizeListener();
        const engine = this.babylon.scene.getEngine();
        // Re-apply DPR + size for first real layout
        if (typeof this.babylon._addGlobalResizeListener === 'function') {
            // already armed; just trigger it by a manual resize
            engine.resize(true);
        } else {
            // safety: do it manually
            engine.setHardwareScalingLevel(1 / (window.devicePixelRatio || 1));
            engine.resize(true);
        }
    }
}