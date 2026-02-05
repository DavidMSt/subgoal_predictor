import os, math, numpy as np, torch, torch_geometric, argparse, random
from torch import nn
from torch.utils.data import DataLoader
from torchvision import datasets, transforms
import numpy as np
from scipy.optimize import linear_sum_assignment
from typing import Tuple

"""
The two towers serve as a first proof of concept using torch.
By having one MLP for the agents and one for the Tasks whose outputs are later combined,
we are able to learn distinct embeddings for agent state vs agent tasks.
Since we are doing supervised learning, the optimal assignment using centralized hungarian can be used as data generator
"""

class TowerSingle(nn.Module):
    def __init__(self, dim_in: int = 4, dim_hidden: list = [128, 64], dim_out = 2) -> None:
        super().__init__()
        
        # define layers
        self.layer_in = nn.Linear(dim_in, dim_hidden[0])
        self.layers_hidden = nn.ModuleList([
            nn.Linear(in_f, out_f) for in_f, out_f in zip(dim_hidden[:-1], dim_hidden[1:])
        ])
        self.layer_out = nn.Linear(dim_hidden[-1], dim_out)

    def forward(self, x):
        x = nn.functional.relu(self.layer_in(x))
        for layer in self.layers_hidden:
            x = nn.functional.relu(layer(x))
        return self.layer_out(x)

class TwoTowers(nn.Module):
    def __init__(self, hidden_d = 64, agent_in = 4, task_in = 4 *args, **kwargs) -> None:
        super().__init__()
        self.hidden_d = hidden_d
        self.tower_agent = TowerSingle(dim_in=agent_in, dim_hidden= [128, 64],dim_out=self.hidden_d)
        self.tower_task = TowerSingle(dim_in=task_in, dim_hidden=[128, 64], dim_out=self.hidden_d)
        self.tower_head = ...

    def forward(self, xA, xT):
        HA = self.tower_agent(xA)
        HT = self.tower_task(xT)
        # assignment_matrix  = HA @ HT.T / math.sqrt(self.hidden_d)
        assignment_matrix  = HA @ HT.T / math.sqrt(self.hidden_d)


        return assignment_matrix

    def assignment_head(self, h_a, h_t):
        d = h_a.shape[0]
        return h_a @ h_t.T/ math.sqrt(d) # division by sqrt for stability
   
# ----- Loss / metric
def rowwise_ce_loss(S: torch.Tensor, y_cols: torch.Tensor) -> torch.Tensor:
    ce_loss = nn.functional.cross_entropy(S, y_cols)
    return ce_loss

@torch.no_grad()
def top1_row_accuracy(S: torch.Tensor, y_cols: torch.Tensor) -> float:
    return (S.argmax(dim=1) == y_cols).float().mean().item()

# ---- Data utils ----
def load_scenes(path: str) -> list[dict]:
    obj = torch.load(path, map_location="cpu")
    if "samples" not in obj: raise ValueError("Dataset missing 'samples'.")

    return obj["samples"]

# TODO: Create training, test and validation set?
def split_scenes(scenes: list[dict], val_ratio: float = 0.15, seed: int = 42) -> Tuple[list[dict], list[dict]]: 
    """ 
    Split all avaiable scenes (= multiple assignment iterations) into train and test set

    Args:
        scenes (list[dict]): _description_
        val_ratio (float, optional): _description_. Defaults to 0.15.
        seed (int, optional): _description_. Defaults to 42.

    Returns:
        Tuple[list[dict], list[dict]]: _description_
    """
    # use random number generator to shuffle range of dataset length
    rng = random.Random(seed)
    idx = list(range(len(scenes))); rng.shuffle(idx)

    # calculate k number of elements in the training set according to val_ratio, 
    # before k is returned as test, after as validation set
    k = int(len(idx) * (1 - val_ratio))
    return [scenes[i] for i in idx[:k]], [scenes[i] for i in idx[k:]]

def scene_tensors(sample: dict, device: torch.device):
    """ 
    Extract torch tensors from a scene

    Args:
        sample (dict): _description_
        device (torch.device): _description_

    Returns:
        _type_: _description_
    """
    XA: torch.Tensor = sample["XA"].to(device)
    XT: torch.Tensor = sample["XT"].to(device)
    y:  torch.Tensor = sample["y_cols"].to(device)
    return XA, XT, y

# ---- Train/Eval ----
@torch.enable_grad()
def train_epoch(model, scenes, opt, device):
    model.train()
    L, A = 0.0, 0.0
    for s in scenes:
        XA, XT, y = scene_tensors(s, device)
        # Assignment matrix prediction
        S = model(XA, XT)
        # 
        loss = rowwise_ce_loss(S, y)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()
        L += loss.item()
        A += top1_row_accuracy(S.detach(), y)
    n = max(1, len(scenes))
    return L/n, A/n

@torch.no_grad()
def eval_epoch(model, scenes, device):
    model.eval()
    L, A = 0.0, 0.0
    for s in scenes:
        XA, XT, y = scene_tensors(s, device)
        # assignment matrix prediction
        S = model(XA, XT)
        # compute loss in current epoch
        L += rowwise_ce_loss(S, y).item()
        A += top1_row_accuracy(S, y)
    n = max(1, len(scenes))
    return L/n, A/n

# ---- CLI ----
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", required=False, help="Path to training_dataset.pt", default = 'applications/master_david/task_assignment/helper/training_dataset.pt')
    p.add_argument("--epochs", type=int, default=300)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--wd", type=float, default=1e-4)
    p.add_argument("--d", type=int, default=32)
    p.add_argument("--device", default="auto", choices=["auto","cpu","cuda"])
    p.add_argument("--save", default=None, help="Path to save model .pt")
    args = p.parse_args()

    device = (
        torch.device("cuda") if args.device=="auto" and torch.cuda.is_available()
        else torch.device(args.device if args.device!="auto" else "cpu")
    )

    scenes = load_scenes(args.data)
    a_in = int(scenes[0]["XA"].shape[1])
    t_in = int(scenes[0]["XT"].shape[1])

    model = TwoTowers(d=args.d, agent_in=a_in, task_in=t_in).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr, weight_decay=args.wd)

    train_s, val_s = split_scenes(scenes, val_ratio=0.15, seed=42)
    # train_s, val_s = [scenes[0]], [scenes[0]]

    for ep in range(1, args.epochs+1):
        trL, trA = train_epoch(model, train_s, opt, device)
        vaL, vaA = eval_epoch(model, val_s, device)
        print(f"epoch {ep:03d} | train loss {trL:.4f} acc {trA:.3f} | val loss {vaL:.4f} acc {vaA:.3f}")

    if args.save:
        torch.save({
            "state_dict": model.state_dict(),
            "latent_dim": args.d,
            "agent_in": a_in,
            "task_in": t_in,
        }, args.save)
        print(f"saved: {args.save}")

if __name__ == "__main__":
    main()

    

