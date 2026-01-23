from core.utils.control.lib_control.il.q_filter import FIR_Design_Params
from core.utils.control.lib_control.il.ilc import BILBO_BUMPED_REFERENCE_TRAJECTORY, BILBO_REFERENCE_LONGER
from core.utils.data import generate_random_input, generate_time_vector_by_length
from robots.bilbo.robot.experiment.experiment_helpers import generate_random_input_trajectory
from robots.bilbo.robot.experiment.multi_trial_experiments import DILC_Experiment_Settings, DILC_Experiment


def dilc_example(bilbo):
    dilc_settings = DILC_Experiment_Settings(
        id='example_dilc',
        description='Example DILC experiment',
        u0=None,
        m0=None,
        reference=BILBO_BUMPED_REFERENCE_TRAJECTORY,
        Ts=0.01,
        J=10,  # Number of trials
        input_lowpass=FIR_Design_Params(
            fc=0.05,
            L=41,
            window='hann'
        ),
        model_lowpass=FIR_Design_Params(
            fc=0.48,
            L=41,
            window='hann'
        )
    )
    t_vector = generate_time_vector_by_length(num_samples=len(dilc_settings.reference), dt=dilc_settings.Ts)
    u0 = generate_random_input(t_vector=t_vector,
                               f_cutoff=1,
                               sigma_I=0.4)

    dilc_settings.u0 = u0

    experiment = DILC_Experiment(bilbo=bilbo,
                                 settings=dilc_settings,
                                 save_path='~/Desktop/dilc_example')

    result = experiment.run()
