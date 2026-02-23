import yaml

if __name__ == '__main__':
    example_dict = {
        'x': 2,
        'y': "Hello"
    }

    yaml.dump(example_dict, open('test.yaml', 'w'))

    # load the yaml back
    with open('test.yaml', 'r') as f:
        # print(yaml.load(f, Loader=yaml.FullLoader))
        x = yaml.safe_load(f)

    print(x)
