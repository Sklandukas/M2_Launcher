class AxisControllerCommands:
    @staticmethod
    def get_identification():
        return "ID?"

    @staticmethod
    def go_home(axis_no):
        return f"H{axis_no}"

    @staticmethod
    def get_position(axis_no):
        return f"P{axis_no}?"

    @staticmethod
    def go_to_position(axis_no, coordinate):
        return f"P{axis_no}{coordinate}"
    
    @staticmethod
    def get_laser():
        return f"LCr rLP50"
    
    @staticmethod
    def set_laser_on():
        return f"LCe 1"
    
    def set_laser_off():
        return f"LCe 0"
    
    @staticmethod
    def get_laser_info():
        return f"LCr i"

    @staticmethod
    def set_laser_power():
        return f"LP50"

    @staticmethod
    def get_cooler_data():
        return "TCr r"    




