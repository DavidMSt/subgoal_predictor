# Refactor Notes Post Thesis
- [x] Introduce continuous position head
- [ ] Use argparser which should parse a given training yaml file instead of having all hparams input via arguments to the training function directly
- [ ] incorporate actual communication rouns between robots by splitting subgoal predictor into a (local) embedding phase and communication rounds which then lead to the final subgoal prediction
- [ ] during training block an OMPL planned robot for the time the OMPL call took on the machine in the simulation -> much closer to real scenario