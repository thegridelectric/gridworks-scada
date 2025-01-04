


def test_home_alone():
    ...
    #  after trigger_house_cold_onpeak_event
    # all relays are direct reports of auto.h.onpeak-backup

    # If scada goes into Admin mode, 
    # HomeAlone top state is Dormant, normal state is Dormant
    # and len(homealone.my_actuators is 0)
    # and relay3 has handle admin.relay3

    # same as above but with atn:
    # relay3 has handle a.aa.relay3

def test_top_state_switches():
    ...
    # When a relay is changed by admin, a
    # new.command.tree is published with all actuators as direct
    # reports of relay  (result of set_admin_command_tree)
    # 
    # TopGoDormant: UsingBackupOnpeak -> Dormant works
    # h.state stays in Dormant
    # h.top_state goes to Dormant
    #
    # TopWakeUp: Dormant -> Normal

