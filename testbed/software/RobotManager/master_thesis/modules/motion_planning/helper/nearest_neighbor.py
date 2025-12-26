import numpy as np
import argparse
import yaml

class Node():
    def __init__(self, q, parent = None, action = None):
        self.position = np.array(q)
        self.children = []
        self.parent = parent

        if parent is not None: 
            parent.add_child(self)
        
        if action is not None:
            self.action = action
        
    def add_child(self, child):
        self.children.append(child)


class NearestNeighbor():
    nodes : list[Node]
    yaml_data: dict
    queries: list[dict]

    def __init__(self):
        self.nodes = []
        self.solutions_indices = []
        self.queries = []

    def parse_arguments(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('nn_data', help='input YAML file with nn data')
        parser.add_argument('output', help='output yaml-file')
        self.args = parser.parse_args()
    
    def configure_from_yaml(self):
        """
        use read data to configure NN instance
        """
        with open(self.args.nn_data, "r") as stream:
            yaml_data = yaml.safe_load(stream)

        for configuration in yaml_data["configurations"]:
            self.add_node(configuration)

        for query in yaml_data["queries"]:
            self.add_query(query)

        # select the correct distance metric to be used for this instance
        self.set_distance_metric(yaml_data["distance"])

    def set_distance_metric(self, metric_str) -> float:
        self.metric_str = metric_str

        def angle_distance(q1, q2):
            """Calculate the minimum distance between two angles (in radians)."""
            diff = (q2 - q1 + np.pi) % (2 * np.pi) - np.pi
            return np.linalg.norm(diff)

        def euclidean_distance(q1, q2):
            return np.linalg.norm(np.array(q1) - np.array(q2))

        if metric_str == "l2":
            self.distance_metric = euclidean_distance

        elif metric_str == "angles" or metric_str == "arm":
            self.distance_metric = angle_distance

        elif metric_str == "se2" or metric_str == "car":
            self.distance_metric = lambda q1, q2: euclidean_distance(q1[:2], q2[:2]) + angle_distance(q1[2:], q2[2:])

        else:
            raise AttributeError(f"Unknown metric string: {metric_str}")

    def nearest_node(self, q):
        node_index = self.nearestK(q,1)[0]
        nearest_node = self.nodes[node_index]
        
        return nearest_node


    def steer_arm(self, q_from, q_to, step_size):
        """
        TODO
        """
        q_from = np.array(q_from)
        q_to = np.array(q_to)
        # Compute difference vector based on metric_str
        if self.metric_str in ("angles", "arm"):
            
            diff = (q_to - q_from + np.pi) % (2 * np.pi) - np.pi

        elif self.metric_str in ("se2", "car"):

            diff_xy = q_to[:2] - q_from[:2]

            diff_theta = (q_to[2:] - q_from[2:] + np.pi) % (2 * np.pi) - np.pi
            diff = np.concatenate((diff_xy, diff_theta))

        else:
            diff = q_to - q_from

        length = np.linalg.norm(diff)
        if length <= step_size or length == 0:
            return tuple(q_to.tolist())

        direction = diff / length
        q_new = q_from + step_size * direction
        # back to [0, 2*pi)
        if self.metric_str in ("angles", "arm"):
            q_new = (q_new + 2 * np.pi) % (2 * np.pi)
        elif self.metric_str in ("se2", "car"):
            # Wrap only the angular components
            q_new_xy = q_new[:2]
            q_new_theta = (q_new[2:] + 2 * np.pi) % (2 * np.pi)
            q_new = np.concatenate((q_new_xy, q_new_theta))
        return tuple(q_new.tolist())
    
    def steer_car(self, q_from, q_to, step_size):
        
        # Convert inputs to NumPy arrays for computation
        q_from = np.array(q_from)
        q_to = np.array(q_to)



    def add_query(self, query):
        self.queries.append(query)
    
    def add_node(self, q, parent= None, action = None, verbose = False):
        self.nodes.append(Node(q, parent, action))
        if verbose:
            print('configuration added:', q)

    def execute_queries(self):
        # reset query solutions
        self.solutions_indices = []
        for query in self.queries:
            if query["type"] == "nearestK":
                solution_indices = self.nearestK(query["q"], query["k"])

            elif query["type"] == "nearestR":
                solution_indices = self.nearestR(query["q"], query["r"])
            
            if len(solution_indices) == 0:
                self.solutions_indices.append([])
            else: 
                self.solutions_indices.append([tuple(self.nodes[i].position.tolist()) for i in solution_indices])

    def nearestK(self, q, k):
        """
        Find the k nearest configurations to a query point
        q: configuration of query point
        k: nearest nodes
        """
        distances = [self.distance_metric(q, node.position) for node in self.nodes]

        sorted_indices = np.argsort(distances)
        indices_nearest_k = sorted_indices[:k]
        return indices_nearest_k
    
    def nearestR(self, q,r):
        """
        q: configuration
        r: distance from q
        """
        distances = [self.distance_metric(q, node.position) for node in self.nodes]
        indices_nearest_r = [i for i, distance in enumerate(distances) if distance < r]
        return indices_nearest_r
    
    def dump_solutions_to_yaml(self):
        """Dump the plan to a yaml file with the given target path"""
        target_path = self.args.output
        data = {
            'results': [[list(pos) for pos in solution] for solution in self.solutions_indices],
        }

        with open(target_path, 'w') as file:
            yaml.dump(data, file, default_flow_style=None, sort_keys=False)
    

if __name__ == "__main__":
    nn = NearestNeighbor()
    nn.parse_arguments() # parse and save all arguments
    nn.configure_from_yaml() # based on arguments configure nn-instance
    nn.execute_queries()
    nn.dump_solutions_to_yaml()
