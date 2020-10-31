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
        pass
# @0
# @(repeat:@i,0,@cpu_count)
#   {
#       "progressBar": {
#           "title": "cpu @i",
#           "max": 100,
#           "fColor": "green",
#           "bColor": "lightGray",
#           "value": "@cpu_stats.cpu_usage_per_core()[@i]"
#       }
#   }
#
# @1
# json
#
# @2
# @line
#
# @3
# json
#
