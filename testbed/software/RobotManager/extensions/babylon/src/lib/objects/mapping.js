import {BabylonBilbo} from "./bilbo/bilbo.js";
import {BabylonFrodo} from "./frodo/frodo.js";
import {BabylonBox, BabylonWall, BabylonWall_Fancy} from "./box/box.js";
import {BabylonFloorInstanced, BabylonSimpleFloor} from "./floor/floor.js";
import {BabylonCircleDrawing, BabylonLineDrawing, BabylonRectangleDrawing} from "./drawings";
import {ArucoStatic} from "./static/static";
import {ClusterTool} from "./clustertool/clustertool";

export let BABYLON_OBJECT_MAPPINGS = {
    'bilbo': BabylonBilbo,
    'bilbo_simple': null,
    'frodo': BabylonFrodo,
    'box': BabylonBox,
    'floor': BabylonFloorInstanced,
    'floor_simple': BabylonSimpleFloor,
    'wall': BabylonWall,
    'wall_fancy': BabylonWall_Fancy,
    "rectangle_drawing": BabylonRectangleDrawing,
    "circle_drawing": BabylonCircleDrawing,
    "line_drawing": BabylonLineDrawing,
    'static': ArucoStatic,
    'clustertool': ClusterTool
}