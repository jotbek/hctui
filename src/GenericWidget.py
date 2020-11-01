class GenericWidget:
    def __init__(self, path):
        self.widgetsDict = {}
        self.parsedDefinition = []

        self.loadWidgets(path)
        self.update()

    def loadWidgets(self, definitionPath):
        definition = self.readFile(definitionPath)
        self.parsedDefinition = self.parseDefinition(definition)

    def readFile(self, path):
        with open(path) as f:
            return f.readlines()

    def update(self):
        pass

    def parseDefinition(self, definition):
        return "definition"
