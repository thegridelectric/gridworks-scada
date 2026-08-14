
class CoreNodeNames:
    """System actor node names, present whatever the plant is.

    Disjoint from HydronicSpaceheatNodeNames, House0NodeNames and
    NolanNodeNames: a name declared here is declared nowhere else.
    """

    primary_scada = "s"
    secondary_scada = "s2"
    asset_power_meter = "power-meter"
    ltn = "ltn"
    leaf_ally = "la"
    admin = "admin"
    auto = "auto"
    derived_generator = "derived-generator"

    # local control and its states
    local_control = "lc"
    local_control_normal = "n"
    local_control_backup = "backup"
    local_control_scada_blind = "scada-blind"
