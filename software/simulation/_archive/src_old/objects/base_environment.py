from extensions.simulation.src import core as core

from extensions.simulation.src.objects.misc.world import DynamicWorld_XYZR_Simple
from extensions.babylon.src.babylon import BabylonVisualization


class EnvironmentBase(core.environment.Environment):
    babylon: (BabylonVisualization, None)
    world: DynamicWorld_XYZR_Simple
    run_mode = 'rt'
    Ts = 0.02
    name = 'environment'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.world = DynamicWorld_XYZR_Simple(name='world', parent=self)

        # Actions
        core.scheduling.Action(action_id='input', object=self, priority=0, parent=self.action_step,
                               function=self.action_input)
        core.scheduling.Action(action_id='controller', object=self, priority=1, parent=self.action_step,
                               function=self.action_controller)
        core.scheduling.Action(action_id='world', object=self, function=self.action_world, priority=2,
                               parent=self.action_step)
        core.scheduling.Action(action_id='visualization', object=self, priority=3, parent=self.action_step,
                               function=self.action_visualization)
        core.scheduling.Action(action_id='output', object=self, priority=4, parent=self.action_step,
                               function=self.action_output)

        core.scheduling.registerActions(self.world, self.scheduling.actions['world'])

    # === ACTIONS ======================================================================================================
    def _init(self, *args, **kwargs):
        ...

    def _action_entry(self, *args, **kwargs):
        super()._action_entry(*args, **kwargs)

    def _action_step(self, *args, **kwargs):
        pass

    def action_input(self, *args, **kwargs):
        pass

    def action_controller(self, *args, **kwargs):
        pass

    def action_visualization(self, *args, **kwargs):
        ...
        # sample = {
        #     'time': self.scheduling.tick_global * self.Ts,
        #     'world': self.world.getSample(),
        #     'settings': getBabylonSettings()
        # }
        # self.babylon.sendSample(sample)

    def action_output(self, *args, **kwargs):
        pass

    def action_world(self, *args, **kwargs):
        pass
