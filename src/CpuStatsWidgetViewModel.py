import cpu_stats


class CpuStatsWidgetViewModel:
    def __init__(self):
        self.cpu_logical_usage = []
        self.cpu_overall_usage = 0
        self.update()

    def get_cpu_logical_usage(self):
        return self.cpu_logical_usage;

    def get_cpu_overall_usage(self):
        return self.cpu_overall_usage

    def update(self):
        self.cpu_logical_usage = cpu_stats.cpu_usage_per_core()
        self.cpu_overall_usage = cpu_stats.cpu_usage_total()
