import traci


SUMO_CFG = "4.sumocfg"  
SUMO_BINARY = "sumo"    

def main():
    traci.start([SUMO_BINARY, "-c", SUMO_CFG])
    tls_ids = traci.trafficlight.getIDList()
    print("Traffic lights:", tls_ids)
    for tls in tls_ids:
        print("== TLS ID:", tls)
        lanes = traci.trafficlight.getControlledLanes(tls)
        lanes = list(dict.fromkeys(lanes))
        print(" Controlled lanes:", lanes)
        for lane in lanes:
            print("  lane", lane, "vehicles:", traci.lane.getLastStepVehicleNumber(lane))
    traci.close()

if __name__ == "__main__":
    main()
