import matplotlib.pyplot as plt
import networkx as nx
import numpy as np


# def connected_subgraphs(adjacency_matrix):
#     """
#     Given an adjacency matrix (as a list of lists or NumPy array),
#     return a list of connected components (subgraphs),
#     where each subgraph is represented as a list of node indices.
#
#     This implementation treats edges as undirected if adjacency_matrix[i][j] is nonzero.
#     (For purely directed graphs, see note below about visited logic.)
#     """
#     n = len(adjacency_matrix)
#     visited = set()
#     subgraphs = []
#
#     for start_node in range(n):
#         if start_node not in visited:
#             # Start a new component (subgraph)
#             stack = [start_node]
#             component = []
#             visited.add(start_node)
#
#             # Depth-First Search (DFS)
#             while stack:
#                 node = stack.pop()
#                 component.append(node)
#
#                 # Check all possible neighbors
#                 for neighbor in range(n):
#                     # If this is an undirected graph, check adjacency_matrix[node][neighbor]
#                     # or adjacency_matrix[neighbor][node].  Here we just check adjacency[node][neighbor].
#                     if adjacency_matrix[node][neighbor] != 0 and neighbor not in visited:
#                         visited.add(neighbor)
#                         stack.append(neighbor)
#
#             subgraphs.append(component)
#
#     return subgraphs
def connected_subgraphs(adjacency_matrix):
    """
    Given an adjacency matrix for a directed graph (which may be non-symmetric),
    return a list of weakly connected components (subgraphs), where each subgraph
    is represented as a list of node indices.

    A weakly connected component is defined as a maximal set of nodes such that,
    if the direction of the edges is ignored, there is a path connecting every pair
    of nodes in the component.

    Parameters:
        adjacency_matrix (list of lists or NumPy array): The directed graph's
            adjacency matrix, where a nonzero entry indicates an edge.

    Returns:
        subgraphs (list of lists): Each inner list contains the node indices that
            belong to the same weakly connected component.
    """
    n = len(adjacency_matrix)
    visited = set()
    subgraphs = []

    for start_node in range(n):
        if start_node not in visited:
            # Begin a new connected component
            stack = [start_node]
            component = []
            visited.add(start_node)

            # Depth-First Search (DFS)
            while stack:
                node = stack.pop()
                component.append(node)
                # For every possible neighbor, check if an edge exists in either direction.
                for neighbor in range(n):
                    if neighbor not in visited and (adjacency_matrix[node][neighbor] != 0 or adjacency_matrix[neighbor][node] != 0):
                        visited.add(neighbor)
                        stack.append(neighbor)

            subgraphs.append(component)

    return subgraphs


def plot_graph_from_adjacency_matrix(adj_matrix):
    """
    Plots a directed graph (which can have multiple unconnected subgraphs)
    given an adjacency matrix. Nodes are displayed as circles with their number,
    and edges are drawn as arrows.

    Parameters:
    - adj_matrix: list of lists or np.ndarray representing the adjacency matrix.
                  A nonzero entry at position (i, j) indicates an edge from node i to node j.
    """
    # Ensure the matrix is a NumPy array for easy indexing
    if not isinstance(adj_matrix, np.ndarray):
        adj_matrix = np.array(adj_matrix)

    adj_matrix = adj_matrix.T
    # Create a directed graph
    G = nx.DiGraph()
    n = adj_matrix.shape[0]

    # Add nodes explicitly (node labels will be their index)
    for i in range(n):
        G.add_node(i)

    # Add edges based on the adjacency matrix
    for i in range(n):
        for j in range(n):
            if adj_matrix[i, j] != 0:
                G.add_edge(i, j)

    # Generate a layout for our nodes - spring layout works well for disconnected graphs too.
    pos = nx.spring_layout(G)

    # Draw nodes with a fixed size and light color
    nx.draw_networkx_nodes(G, pos, node_size=500, node_color='lightblue')

    # Draw directed edges with arrows
    nx.draw_networkx_edges(G, pos, arrowstyle='-|>', arrowsize=20)

    # Label nodes with their number
    labels = {i: str(i) for i in G.nodes()}
    nx.draw_networkx_labels(G, pos, labels, font_size=12, font_color='black')

    # Remove axis for clarity and display the plot
    plt.axis('off')
    plt.show()

if __name__ == "__main__":
    # Example: an undirected adjacency matrix (5x5)
    # Graph has two components:
    #   component 1: nodes (0,1)
    #   component 2: nodes (2,3,4)
    sample_adj_matrix = [
        [0, 1, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 1],
        [0, 0, 1, 0]
    ]

    print("Connected subgraphs:", connected_subgraphs(sample_adj_matrix))

    plot_graph_from_adjacency_matrix(sample_adj_matrix)
