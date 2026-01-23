def is_subpath(path1: str, path2: str) -> bool:
    """
    Returns True if path2 is the same as path1 or is nested under path1.

    Examples:
      is_subpath("/a/b", "/a/b")       -> True
      is_subpath("/a/b", "/a/b/c")     -> True
      is_subpath("/a/b", "/a/bc")      -> False
      is_subpath("/a/b", "/a/x")       -> False
    """
    # Remove any leading/trailing slashes and split into segments
    segs1 = [s for s in path1.strip("/").split("/") if s]
    segs2 = [s for s in path2.strip("/").split("/") if s]

    # path2 must have at least as many segments as path1
    if len(segs2) < len(segs1):
        return False

    # check that every segment of path1 matches the corresponding in path2
    return segs2[:len(segs1)] == segs1