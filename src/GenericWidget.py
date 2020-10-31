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

# @new,@line_box
# @json(repeat:@i,0,@cpu_count)
#   {
#       "progressBar": {
#           "title": "cpu @i: ",
#           "max": 100,
#           "fColor": "green",
#           "bColor": "lightGray",
#           "value": "@cpu_stats.cpu_usage_per_core()[@i]"
#       }
#   }
#
# @new
# @json
#
# @new
# @line
#
# @new
# @json
#
