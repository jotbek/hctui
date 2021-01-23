import json


def get_view(self, path):
    with open(path) as f:
        definition = json.load(f)
    return self.generate_widget(definition)


def generate_widget(self, definition):
    pass
