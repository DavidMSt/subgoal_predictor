from __future__ import annotations  # enable postponed evaluation of annotations
import dataclasses
import logging
import re
from abc import ABC, abstractmethod
from typing import Union

import extensions.simulation.src.core.spaces as core_spaces
import extensions.simulation.src.core.scheduling as scheduling
import extensions.simulation.src.core.physics as physics

from extensions.simulation.src.utils.babylon import setBabylonSettings
import numpy as np


# ======================================================================================================================
@dataclasses.dataclass
class CollisionSettings:
    """
    Settings to control collision checking for a world object.

    Attributes:
        check (bool): Whether to perform collision checking.
        collidable (bool): Whether the object can collide with others.
        includes (list[type]): List of classes to include in collision checks.
        excludes (list[type]): List of classes to exclude from collision checks.
    """
    check: bool = False
    collidable: bool = True
    # Use a lambda to delay evaluation of WorldObject until runtime.
    includes: list[type] = dataclasses.field(default_factory=lambda: [globals()['Object']])
    excludes: list[type] = dataclasses.field(default_factory=list)


# ======================================================================================================================
@dataclasses.dataclass
class CollisionData:
    """
    Data container for collision information.

    Attributes:
        settings (CollisionSettings): The collision settings.
        collision_state (bool): Current collision state.
        collision_objects (list): List of objects currently in collision.
    """
    settings: CollisionSettings = dataclasses.field(default_factory=CollisionSettings)
    collision_state: bool = False
    collision_objects: list = dataclasses.field(default_factory=list)


# ======================================================================================================================
@dataclasses.dataclass
class EnvironmentObjectVisualization:
    """
    Visualization data for a world object.

    Attributes:
        static (bool): Whether the visualization is static.
        sample_flag (bool): Flag to indicate if there is a new visualization sample.
        _sample (dict): Internal storage for the visualization sample.
    """
    static: bool = False
    sample_flag: bool = False
    _sample: dict = dataclasses.field(default_factory=dict)

    @property
    def sample(self) -> dict:
        return self._sample

    @sample.setter
    def sample(self, value: dict):
        self._sample = value
        self.sample_flag = True

    def getSample(self) -> dict:
        """
        Returns and resets the current visualization sample.
        """
        sample = self.sample
        self._sample = {}
        self.sample_flag = False
        return sample


# ======================================================================================================================
class Object(scheduling.ScheduledObject):
    """
    Base class for all objects in the world.

    Each object is uniquely identified by its 'id'. Objects can be scheduled, have physics,
    visualization, and collision properties.
    """
    # Type annotations for attributes (these may be set externally)
    env: Environment
    space: core_spaces.Space
    _configuration: core_spaces.State
    space_global: core_spaces.Space
    configuration_global: core_spaces.State
    group: ObjectGroup
    physics: physics.PhysicalBody
    collision: CollisionData
    id: str  # Unique identifier for the object
    object_type: str = 'object'
    static: bool = False
    visualization: EnvironmentObjectVisualization

    def __init__(self,
                 object_id: str = None,
                 env: Environment = None,
                 group: ObjectGroup = None,
                 space: core_spaces.Space = None,
                 *args, **kwargs):
        """
        Initialize a WorldObject.

        Args:
            object_id (str): Unique identifier. If None, a default id is generated.
            world (Environment): The world to which this object belongs.
            group (ObjectGroup): The group that contains this object.
            space (core_spaces.Space): The space in which the object is defined.
        """
        # Set unique id; if not provided, generate one using the class name and object id.
        if object_id is None:
            self.id = f"{type(self).__name__}_{id(self)}"
        else:
            self.id = object_id

        self._configuration = None
        self.sample_flag = False  # Flag for tracking configuration updates

        super().__init__()

        self.env = env
        self.group = group

        # If the object is part of a group, adopt the group's world
        if self.group is not None and self.group.world is not None:
            self.env = self.group.world

        # Set the object's space. If both an argument and group space exist, prefer the group’s space.
        if self.group is not None and getattr(self.group, 'space', None) is not None:
            self.space = self.group.space
        elif space is not None:
            self.space = space

        # Add object to its group (if any) and world (if any)
        if self.group is not None and hasattr(self.group, 'addObject'):
            self.group.addObject(self)
        if self.env is not None and hasattr(self.env, 'addObject'):
            self.env.addObject(self)

        # Initialize configuration from the space state if available
        if self.space is not None:
            self._configuration = self.space.getState()

        self.collision = CollisionData()
        self.visualization = EnvironmentObjectVisualization()

        # Register physics update action if the object is not static
        if not self.static:
            scheduling.Action(
                action_id='physics_update',
                function=self._updatePhysics,
                lambdas={'config': lambda: self.configuration},
                object=self
            )

    # === PROPERTIES ================================================================================================
    @property
    def configuration(self):
        """Return the current configuration (state) of the object."""
        return self._configuration

    @configuration.setter
    def configuration(self, value):
        """
        Set the configuration (state) of the object.

        Args:
            value: New state to be set.
        """
        if value is not None and self.space is not None:
            self.sample_flag = True
            # Assume that _configuration has a 'set' method for updating its state.
            self._configuration.set(value)

    @property
    def configuration_global(self):
        """
        Return the configuration mapped to the global space.
        Assumes that the space_global mapping is defined.
        """
        return self.space_global.map(self.configuration)

    @configuration_global.setter
    def configuration_global(self, value):
        raise Exception("Not implemented yet")

    # === METHODS ===================================================================================================
    def getSample(self) -> dict:
        """
        Get a sample representation of the object's state.
        """
        return self._getSample()

    def getVisualizationSample(self) -> dict:
        """
        Get a sample combining the object's state and visualization data.
        """
        sample = self._getSample()
        sample_visualization = self.visualization.getSample()
        return {**sample, **sample_visualization}

    def getParameters(self) -> dict:
        """
        Get parameters describing the object (used in configuration generation).
        """
        return self._getParameters()

    def translate(self, vector, space='local'):
        """
        Translate the object by a given vector.

        Args:
            vector: Translation vector.
            space (str or core_spaces.Space): The space in which translation is applied.
        """
        # Implementation goes here.
        ...

    def rotate(self, rotation, space='local'):
        """
        Rotate the object.

        Args:
            rotation: Rotation value.
            space (str or core_spaces.Space): The space in which rotation is applied.
        """
        # Implementation goes here.
        ...

    def setConfiguration(self, value, dimension=None, subdimension=None, space='local'):
        """
        Set (or update) the object's configuration.

        Args:
            value: New configuration value or update.
            dimension: If provided, update only a specific dimension.
            subdimension: If provided, update a subdimension.
            space (str or core_spaces.Space): Whether to use local or global space.
        """
        assert (space == 'local' or space == 'global' or space == self.space or space == self.space_global)
        self.sample_flag = True
        config_temp = self.space.map(self._configuration)
        if dimension is None:
            self.configuration = value
        else:
            if subdimension is None:
                self._configuration[dimension] = value
            else:
                self._configuration[dimension][subdimension] = value

        self._updatePhysics(self.configuration)

        # If this object is a group, update physics for all contained objects.
        if isinstance(self, ObjectGroup):
            for _, obj in self.objects.items():
                obj._updatePhysics(obj.configuration)

    def setPosition(self, value=None, dimension=None, **kwargs):
        """
        Set the object's position.

        Args:
            value: Position value if setting all coordinates.
            dimension: Specific coordinate to update.
            kwargs: Alternatively, keyword arguments for coordinate updates.
        """
        assert (self.space.hasDimension('pos'))
        if dimension is None and len(kwargs) == 0:
            self.setConfiguration(dimension='pos', value=value)
        elif dimension is not None:
            self.setConfiguration(dimension='pos', subdimension=dimension, value=value)
        elif len(kwargs) > 0:
            for key, key_value in kwargs.items():
                self.setConfiguration(dimension='pos', subdimension=key, value=key_value)

    def setOrientation(self, value):
        """
        Set the object's orientation.

        Args:
            value: New orientation value.
        """
        assert (self.space.hasDimension('ori'))
        self.setConfiguration(dimension='ori', value=value)

    def getConfiguration(self, space='local'):
        """
        Get the object's configuration in the specified space.

        Args:
            space (str or core_spaces.Space): 'local' or 'global' (or a specific space).

        Returns:
            The object's configuration.
        """
        assert (space == 'local' or space == 'global' or space == self.space or space == self.space_global)
        if space == 'local' or space == self.space:
            return self.configuration
        else:
            return self.configuration_global

    def _onAdd_callback(self):
        """
        Callback that is called when the object is added to a world or group.
        """
        # Implementation can be provided as needed.
        ...

    # === ABSTRACT / HELPER METHODS ================================================================================
    def _getParameters(self) -> dict:
        """
        Generate a dictionary of parameters describing the object.
        """
        parameters = {
            'object_type': self.object_type,
            'id': self.id,
            'configuration': self.configuration_global.serialize(),
            'class': self.__class__.__name__
        }
        return parameters

    def _getSample(self) -> dict:
        """
        Generate a sample dictionary representing the object's current state.
        """
        sample = {
            'id': self.id,
            'configuration': self.configuration_global.serialize(),
            'parameters': self.getParameters()
        }
        return sample

    def _updatePhysics(self, config=None, *args, **kwargs):
        """
        Update the physics state of the object.

        Args:
            config: The configuration to update from. Defaults to the global configuration.
        """
        if config is None:
            config = self.configuration_global
        if hasattr(self, 'physics') and self.physics is not None:
            self.physics.update(config=self.configuration_global)

    def _init(self):
        """
        Additional initialization can be performed here.
        """
        pass

    # === BUILT-INS =================================================================================================
    def __repr__(self):
        return f"{str(self.configuration)} (global: {str(self.configuration_global)})"


# ======================================================================================================================
class ObjectGroup(Object):
    """
    A group of WorldObjects.

    WorldObjectGroup is itself a WorldObject, but it can contain multiple other objects.
    """
    objects: dict[str, Object]
    local_space: core_spaces.Space
    object_type = 'group'

    def __init__(self,
                 object_id: str = None,
                 env: Environment = None,
                 objects: list[Object] = None,
                 local_space: core_spaces.Space = None,
                 *args, **kwargs):
        """
        Initialize a WorldObjectGroup.

        Args:
            object_id (str): Unique identifier for the group.
            env (Environment): The world in which the group exists.
            objects (list[Object]): Initial list of objects in the group.
            local_space (core_spaces.Space): The local space for the group.
        """
        super().__init__(object_id=object_id, env=env, *args, **kwargs)

        # Ensure that the group's space matches the world's space
        assert (self.space == self.env.space)

        # Disable collision for groups
        self.collision.settings.collidable = False

        if local_space is not None:
            self.local_space = local_space
            self.local_space.parent = self.env.space
            self.local_space.origin = self.configuration

        self.objects = {}

        if objects is not None:
            for obj in objects:
                self.addObject(obj)

    def addObject(self, object: Union[Object, list[Object]]):
        """
        Add one or more WorldObjects to the group.

        Args:
            object (Object or list[Object]): The object(s) to add.
        """
        # If a single object is provided, wrap it in a list.
        if isinstance(object, Object):
            object = [object]

        for obj in object:
            assert isinstance(obj, Object)

            # Check if the object already exists in the group.
            if obj in self.objects.values():
                logging.warning("Object already exists in group")
                continue

            # Check for duplicate id within the group.
            for _, other in self.objects.items():
                if obj.id == other.group_id:
                    logging.warning(f"There already exists an object with id \"{obj.id}\" in the group.")
                    break

            # Set the object's world and space
            obj.env = self.env
            if hasattr(self, 'local_space') and self.local_space is not None:
                obj.space = self.local_space

            # Add the object to the dictionary using its unique id.
            self.objects[obj.id] = obj

            logging.info(f"Added Object \"{obj.id}\" ({type(obj)}) to the group {self.id}")

    def _updatePhysics(self, config, *args, **kwargs):
        """
        Update physics for the group.

        (A proper implementation should update the physics of contained objects, if needed.)
        """
        pass


# ======================================================================================================================
class Environment(scheduling.ScheduledObject):
    """
    The world container holds all world objects and agents.

    It manages adding, removing, updating objects and performing global operations such as
    collision checking and physics updates.
    """

    scheduler: scheduling.Scheduler
    space: core_spaces.Space

    Ts: float

    objects: dict[str, Object]
    agents: dict[str, Object]
    name = 'env'

    # size: dict  # World dimensions; this is separate from the space definition.

    def __init__(self, Ts, run_mode: str = None, space: core_spaces.Space = None, size=None, *args, **kwargs):
        """
        Initialize the world.

        Args:
            space (core_spaces.Space): The global space of the world.
            size (dict): Dimensions of the world.
        """
        super().__init__(*args, **kwargs)

        self.Ts = Ts
        self.run_mode = run_mode

        if not hasattr(self, 'space'):
            assert space is not None, "A space must be provided for the world."
            self.space = space

        self.objects = {}
        self.agents = {}

        self.action_step = scheduling.Action(action_id='step', object=self)
        self.scheduling.actions['_entry'].parent = self.action_step

        self.scheduling.actions['_entry'].priority = 0
        self.scheduling.actions['_exit'].parent = self.action_step
        self.scheduling.actions['_exit'].priority = 1000

        self.scheduler = scheduling.Scheduler(action=self.action_step, mode=self.run_mode, Ts=self.Ts)
        # self.size = size
        #
        # if self.size is not None:
        #     raise NotImplementedError("Setting world size is not implemented yet.")

    def step(self, *args, **kwargs):
        self.scheduling.actions['step'].run(*args, **kwargs)

    def start(self, *args, **kwargs):
        self.scheduler.run(*args, **kwargs)

    def init(self, *args, **kwargs):
        self.scheduling.actions['_init'].run(*args, **kwargs)

    def addObject(self, objects: Union[Object, list[Object]]):
        """
        Add one or more WorldObjects to the world.

        Args:
            objects (Object or list[Object]): Object(s) to add.
        """
        if not isinstance(objects, list):
            objects = [objects]

        for obj in objects:
            assert isinstance(obj, Object)

            # Warn if the object already exists in the world.
            if obj in self.objects.values():
                logging.warning("Object already exists in world")
                continue

            for _, other in self.objects.items():
                if obj.id == other.id:
                    logging.warning(f"There already exists an object with id \"{obj.id}\" in the world.")
                    break

            # Register the object with the world's scheduler and set its world and space.
            obj.scheduling.parent = self
            obj.env = self
            obj.space_global = self.space

            # If the object has a dedicated space, ensure it maps to the global space.
            if hasattr(obj, 'space') and obj.space is not None:
                assert (obj.space.hasMapping(self.space))
            else:
                obj.space = self.space

            self.objects[obj.id] = obj

            logging.info(f"Added Object \"{obj.id}\" ({type(obj)}) to the world.")

            # Call the object's on-add callback.
            obj._onAdd_callback()

    def removeObject(self, objects: Union[list[Object], Object]):
        """
        Remove one or more objects from the world.

        Args:
            objects (Object or list[Object]): The object(s) to remove.
        """
        if not isinstance(objects, list):
            objects = [objects]

        for obj in objects:
            assert isinstance(obj, Object)
            if obj in self.objects.values():
                del self.objects[obj.id]
            # TODO: Also deregister the simulation object.
            self.removeChild(obj)

    def addAgent(self, agent: Object):
        """
        Add an agent to the world.

        Args:
            agent (Object): The agent to add.
        """
        self.agents[agent.id] = agent

        if agent.id not in self.objects:
            self.addObject(agent)

    def getObjectsByID(self, id: str, regex=False) -> list[Object]:
        """
        Retrieve objects by their unique id.

        Args:
            id (str): The id to search for.
            regex (bool): Whether to treat the id as a regular expression.

        Returns:
            List of matching WorldObjects.
        """
        result = []

        if not regex:
            for obj in self.objects.values():
                if obj.id == id:
                    result.append(obj)
        else:
            for obj in self.objects.values():
                if re.search(id, obj.id):
                    result.append(obj)

        return result

    def getObjectsByType(self, type_: type) -> list[Object]:
        """
        Retrieve objects by their type.

        Args:
            type_ (type): The type to filter by.

        Returns:
            List of WorldObjects of the given type.
        """
        result = [obj for obj in self.objects.values() if isinstance(obj, type_)]
        return result

    def physicsUpdate(self):
        """
        Update the physics state of all objects in the world.
        """
        for obj in self.objects.values():
            if hasattr(obj, 'physics') and obj.physics is not None:
                obj.scheduling.actions['physics_update']()

    def getSample(self) -> dict:
        """
        Generate a sample dictionary representing the current state of the world.

        Returns:
            dict: A dictionary mapping object ids to their current state samples.
        """
        sample = {'objects': {}}

        for obj in self.objects.values():
            # Update sample for dynamic objects or if a static object's state has been flagged as changed.
            if not obj.static or (obj.static and obj.sample_flag):
                sample['objects'][obj.id] = obj.getSample()

        return sample

    def getVisualizationSample(self) -> dict:
        """
        Generate a sample dictionary for visualization purposes.

        Returns:
            dict: A dictionary mapping object ids to their visualization samples.
        """

        objects_sample = {}
        for obj in self.objects.values():
            if not obj.static or (obj.static and obj.visualization.sample_flag):
                objects_sample[obj.id] = obj.getVisualizationSample()

        sample = {
            'time': self.scheduling.tick_global * self.Ts,
            'objects': objects_sample,
            'settings': {}
        }

        return sample

    def generateWorldConfig(self) -> dict:
        """
        Generate the configuration for the world by gathering parameters from all objects.

        Returns:
            dict: World configuration dictionary.
        """
        world_definition = {'objects': {}}

        for object_id, obj in self.objects.items():
            world_definition['objects'][object_id] = obj.getParameters()

        return world_definition

    def setSize(self, **kwargs):
        """
        Set the dimensions of the world.

        The size is determined by the dimensions defined in the world's space.

        Args:
            kwargs: Dimension names and their corresponding size values (as lists).
        """
        self.size = {}
        if self.space.hasDimension('pos'):
            self.size['pos'] = {}
            for dim, value in kwargs.items():
                if dim in self.space['pos']:
                    assert isinstance(value, list)
                    self.size['pos'][dim] = value
        else:
            for dim, value in kwargs.items():
                if self.space.hasDimension(dim):
                    assert isinstance(value, list)
                    self.size[dim] = value

    def collisionCheck(self):
        """
        Perform collision checking for objects in the world.

        For each object that requires collision checking, compare against all other objects (respecting
        inclusion and exclusion lists) and update collision information accordingly.
        """
        for key, obj in self.objects.items():
            if obj.collision.settings.check:
                obj.physics.collision.collision_state = False
                for _, collision_object in self.objects.items():
                    if collision_object is obj:
                        continue
                    if collision_object.collision.settings.collidable:
                        # Check if the collision_object's type is included.
                        if any(isinstance(collision_object, include_class)
                               for include_class in obj.collision.settings.includes):
                            # Ensure it is not in the exclusion list.
                            if not any(isinstance(collision_object, exclude_class)
                                       for exclude_class in obj.collision.settings.excludes):
                                # Insert proximity and collision checking code here.
                                ...

    def _init(self):
        """
        Additional initialization: build the action tree for all objects.
        """
        # Iterate over all objects and assign parent actions where applicable.
        for obj in self.objects.values():
            for action_name, action in self.scheduling.actions.items():
                if action_name in obj.scheduling.actions and not action_name.startswith("_"):
                    obj.scheduling.actions[action_name].parent = action

    def _action_entry(self, *args, **kwargs):
        super()._action_entry()
        self.scheduling.tick += 1
        self.scheduling.tick_global = self.scheduling.tick

    def _action_start(self, *args, **kwargs):
        super()._action_start()
        self.scheduling.tick = 0
        self.scheduling.tick_global = 0
