# Training Run Mapping
Maps published names → original names + warm-start chain.
★ = checkpoint selected for evaluation (run_eval.py).
a/b/c suffix = resumed segments of the same experimental stage.

## A_mlp
| Published name | Original name | Selected |
|---|---|:---:|
| `A_mlp_stage1b` | `stage1b_20260324_103903` | ★ |

## A_mlp_discrete
| Published name | Original name | Selected |
|---|---|:---:|
| `A_mlp_disc_v2a` | `stage2-scratch-v2_20260328_101252` |  |
| `A_mlp_disc_v2b` | `stage2-scratch-v2_20260329_123527` |  |

## A_hom_gnn_discrete
| Published name | Original name | Selected |
|---|---|:---:|
| `A_hom_gnn_disc` | `gnn_ppo_D2_20260403_221437` |  |

## A_hom_gnn
| Published name | Original name | Selected |
|---|---|:---:|
| `A_hom_gnn_base` | `gnn_ppo_D2_cont_20260406_144831` |  |
| `A_hom_gnn_v2` | `gnn_ppo_D2_cont_v2_20260407_160009` |  |
| `A_hom_gnn_v3a` | `gnn_ppo_D2_cont_v3_20260408_153650` |  |
| `A_hom_gnn_v3b` | `gnn_ppo_D2_cont_v3_20260409_125024` |  |
| `A_hom_gnn_v3c` | `gnn_ppo_D2_cont_v3_20260411_174544` |  |
| `A_hom_gnn_phase2` | `gnn_ppo_D2_cont_v3_phase2_20260412_224158` | ★ |

## A_bi_gnn
| Published name | Original name | Selected |
|---|---|:---:|
| `A_bi_gnn_base` | `bp_A_20260414_005433` |  |
| `A_bi_gnn_ft2` | `bp_A_ft2_20260416_094315` | ★ |
| `A_bi_gnn_ft3` | `bp_A_ft3_20260416_235148` |  |
| `A_bi_gnn_ft4` | `bp_A_ft4_20260419_021501` |  |
| `A_bi_gnn_ft5` | `bp_A_ft5_20260420_121017` |  |

## C_bi_gnn
| Published name | Original name | Selected |
|---|---|:---:|
| `C_bi_gnn_v1` | `bp_C_20260415_140332` |  |
| `C_bi_gnn_v2` | `bp_C_20260417_181304` |  |
| `C_bi_gnn_v3` | `bp_C_20260420_235105` | ★ |
| `C_bi_gnn_v4` | `bp_C2_20260423_232318` |  |

## D_bi_gnn
| Published name | Original name | Selected |
|---|---|:---:|
| `D_bi_gnn_v1` | `bp_D_20260415_110413` |  |
| `D_bi_gnn_v2` | `bp_D2_20260419_234212` |  |
| `D_bi_gnn_v3` | `bp_D2_20260421_144251` | ★ |
| `D_bi_gnn_v4` | `bp_D3_20260423_231814` |  |
