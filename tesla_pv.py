"""
Description

@author: Bernd Kast
@copyright: Copyright (c) 2018, Siemens AG
@note:  All rights reserved.
"""
import os
from datetime import datetime, timedelta
from math import ceil, floor

import numpy as np
import paho.mqtt.client as mqtt
import teslapy
import json

print("starting", flush=True)
with open("/data/options.json", "r") as fp:
    options = json.load(fp)
MAIL = options['TESLA_MAIL']
change_of_charge_power = False
car_index_mapping = dict()

with teslapy.Tesla(MAIL, timeout=120, retry=teslapy.Retry(total=3, status_forcelist=(418, 500, 502, 503, 504))) as tesla:
    class HistoricData(object):
        def __init__(self):
            self.timestamp = None
            self.power_history = None
            self.car_indices = len(options['EMPTY_SOC'].split(";"))
            self.car = [dict() for _ in range(self.car_indices)]
            self.last_car_index = 0
            self.check_period_minutes = 0.5
            self.reset()

        def reset(self):
            self.power_history = list()
            self.timestamp = datetime.now()

        def add(self, topic, data):
            try:
                # print(topic, flush=True)
                # if "vzlogger" in topic:
                if option["MQTT_GRID_POWER_TOPIC"] in topic:
                    self.power_history.append(float(data.decode("ASCII")))
                elif option["MQTT_TESLAMATE_TOPIC"] in topic:
                    car_index = int(topic.split("/")[-2]) - 1
                    # print(f"car_index: {car_index}: {data.decode('ASCII') V3#V3}", flush=True)
                    self.car[car_index][topic.split("/")[-1]] = data.decode("ASCII")
                else:
                    print(f"unknown topic: {topic} with data: {data}", flush=True)

                if datetime.now() - self.timestamp > timedelta(minutes=self.check_period_minutes):
                    if len(self.power_history) > 10:
                       for _ in range(self.car_indices):
                          self.last_car_index += 1
                          if self.last_car_index >= self.car_indices:
                              self.last_car_index = 0
                          car_index = self.last_car_index
                          car = self.car[car_index]
                          if not car["latitude"].startswith(options["HOME_LAT"]) or not car["longitude"].startswith(options["HOME_LON"]):
                             print(f"skipping car {car_index} as it is not home: lat: {car['latitude']}/{options['HOME_LAT']} lon:{car['longitude']}/{options['HOME_LON']}")
                             continue
                          print(f"updating car {car_index}")
                          print(car)
                          update_charge_speed(car_index,
                                              True,
                                              car["plugged_in"] == "true",
                                              float(car["battery_level"]),
                                              float(car["charger_actual_current"]),
                                              float(car["charger_power"]),
                                              float(car["charge_limit_soc"]),
                                              float(car["odometer"]),
                                              np.array(self.power_history))
                          self.reset()
            except Exception as e:
                print("Exception occured in add: {e}")


    historic_data = HistoricData()
    print("initialized", flush=True)

    def checked_wake_up(v):
        for _ in range(5):
            if not v.available():
                print("start wakeup")
                try:
                    v.sync_wake_up()
                except Exception as e:
                    print(f"Exception occurred: {e}")
            else:
                print("vehicle is online")
                break


    def get_vehicle(car_index, odom):
        token = options['TESLA_TOKEN']
        print(f"already authorized: {tesla.authorized}", flush=True)
        if not tesla.authorized:
            tesla.refresh_token(refresh_token=token)
        try:
            vehicles = tesla.vehicle_list()
        except:
            tesla.refresh_token(refresh_token=token)
            vehicles = tesla.vehicle_list()
        global car_index_mapping
        print(f"car_index_mapping: {car_index_mapping}")
        if car_index in car_index_mapping:
            vehicle = vehicles[car_index_mapping[car_index]]
        else:
            vehicle = None
            i = 0
            for v in vehicles:
                checked_wake_up(v)
                print(f"car {i} has {float(v['vehicle_state']['odometer']) * 1.60934} km")
                if abs(float(v["vehicle_state"]["odometer"]) * 1.60934 - odom) < 2.0:
                    vehicle = v
                    car_index_mapping[car_index] = i
                i += 1
            if not vehicle:
                print(f"ERROR: no car with odom {odom} found")
                return
        checked_wake_up(vehicle)
        print(f"model of found vehicle: {vehicle['vehicle_config']['car_type']}")
        return vehicle


    def set_charging(car_index, odom, start):
        print(f"{str(datetime.now())} start charging: {start}", flush=True)
        vehicle = get_vehicle(car_index, odom)
        try:
            if start:
                vehicle.command('START_CHARGE')
            else:
                vehicle.command('STOP_CHARGE')
        except Exception as e:
            print(e, flush=True)


    def set_charge_speed(car_index, odom, amperage, do_not_interfere_amperage):
        vehicle = get_vehicle(car_index, odom)
        print("start wakeup")
        checked_wake_up(vehicle)
        cur_amps = vehicle["charge_state"]["charge_current_request"]
        print(f"cur_amps: {cur_amps}, amps: {amperage}, dni: {do_not_interfere_amperage}")
        if cur_amps < do_not_interfere_amperage and \
                cur_amps != amperage:
            print(f"set amperage for car with odometer {odom}: {amperage} was {cur_amps}", flush=True)
            vehicle.command("CHARGING_AMPS", charging_amps=amperage)
            global change_of_charge_power
            change_of_charge_power = True
            print(f"{str(datetime.now())}: amperage set", flush=True)


    def update_charge_speed(car_index: int, twc_is_connected: bool, car_plugged: bool, soc: float, current_amperage: float, current_charge_power: float, charge_limit_soc: float, odom: float, power_history: np.array) -> object:
        empty_soc = int(options['EMPTY_SOC'].split(";")[car_index])  # soc below the car is considered empty => full charging speed
        mid_soc = int(options['MID_SOC'].split(";")[car_index])  # soc until we want to charge every bit of produced pv power
        do_not_interfere_charge_limit_soc = int(options['DO_NOT_INTERFERE_CHARGE_LIMIT'].split(";")[car_index])

        do_not_interfere_amperage = int(options['DO_NOT_INTERFERE_AMPERAGE'].split(";")[car_index])
        min_amperage = int(options['MIN_AMPERAGE'].split(";")[car_index])
        effective_voltage = int(options['EFFECTIVE_VOLTAGE'].split(";")[car_index])

        print(f"empty_soc: {empty_soc}, mid_soc: {mid_soc}, do_not_interfere_charge_limit_soc: {do_not_interfere_charge_limit_soc}, do_not_interfere_amperage: {do_not_interfere_amperage}, min_amperage: {min_amperage}")

        # strip first 10 seconds after power change as the charger needs to ramp up (to avoid oszillation)
        global change_of_charge_power
        if change_of_charge_power:
            print(f"strip first seconds because we lately changed the charging speed size: {len(power_history)}", flush=True)
            change_of_charge_power = False
            try:
                power_history = power_history[10:]
            except:
                print(f"Power history was too short, could not strip first 10s: {len(power_history)}", flush=True)

        # if we charge at home
        if twc_is_connected:
            # check if vehicle is plugged in as well
            if car_plugged:
                print(f"current_amperage: {current_amperage}", flush=True)
                print(f"current_charge_limit: {charge_limit_soc}", flush=True)
                if current_amperage >= do_not_interfere_amperage or \
                    charge_limit_soc >= do_not_interfere_charge_limit_soc:
                    print("do_not_interfere", flush=True)
                    return
                if soc < empty_soc:
                    new_amperage = do_not_interfere_amperage - 1
                    new_do_charging = True
                else:
                    if not effective_voltage:
                        try:
                            effective_voltage = round(current_charge_power * 1000.0 / current_amperage / 230.0) * 230.0
                        except ZeroDivisionError:
                            effective_voltage = 230.0 * 3.0
                        effective_voltage = max(230.0, effective_voltage)
                    else:
                        effective_voltage = 3.0 * 230.0

                    consumption_history = power_history - effective_voltage * current_amperage
                    # calculate optimal charge power based on current soc
                    if soc < mid_soc:
                        if abs(np.min(power_history)) < 50:        # hysteresis
                            print(f"Deviation too small - keeping old chargespeed min: {np.min(power_history)}", flush=True)
                            return
                        new_charge_power = -np.min(consumption_history)
                        new_amperage = ceil(new_charge_power / effective_voltage)
                        print(f"Chargepower (mix): {new_charge_power} W => {new_amperage} A (mean:{np.mean(consumption_history)}; max: {np.max(consumption_history)}", flush=True)
                        if new_amperage <= 0:
                            new_amperage = min_amperage
                            new_do_charging = False
                        else:
                            new_do_charging = True
                    else:
                        if abs(np.max(power_history)) < 50:        # hysteresis
                            print(f"Deviation too small - keeping old chargespeed max: {np.max(power_history)}", flush=True)
                            return
                        new_charge_power = -np.max(consumption_history)
                        new_amperage = floor(new_charge_power / effective_voltage)
                        print(f"Chargepower (PV only): {new_charge_power} W => {new_amperage} A", flush=True)
                        if new_amperage < min_amperage:
                            new_amperage = min_amperage
                            new_do_charging = False
                        else:
                            new_do_charging = True
                for _ in range(3):
                    try:
                        if (current_charge_power > 0.1) != new_do_charging:
                            set_charging(car_index, odom, new_do_charging)
                        if new_do_charging:
                            new_amperage = max(new_amperage, min_amperage)
                            if new_amperage != current_amperage:
                                set_charge_speed(car_index, odom, new_amperage, do_not_interfere_amperage)
                        break
                    except Exception as e:
                        print(f"retry due to exception {e}")
                        continue
    # The callback for when the client receives a CONNACK response from the server.
    def on_connect(client, userdata, flags, rc):
        print("Connected with result code " + str(rc), flush=True)
        # Subscribing in on_connect() means that if we lose the connection and
        # reconnect then subscriptions will be renewed.
        # client.subscribe("teslamate/teslamate/cars/#")
        # client.subscribe("vzlogger/data/chn2/raw")
        client.subscribe(option["MQTT_TESLAMATE_TOPIC"])
        client.subscribe(option["vzlogger/data/chn2/raw"])


    # The callback for when a PUBLISH message is received from the server.
    def on_message(client, userdata, msg):
        global historic_data
        historic_data.add(msg.topic, msg.payload)
        # print(msg.topic + " " + str(msg.payload), flush=True)


    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.username_pw_set(options['MQTT_USER'], options['MQTT_PW'])
    client.connect(options['MQTT_HOST'], int(options['MQTT_PORT']), 60)
    print("connected", flush=True)
    # Blocking call that processes network traffic, dispatches callbacks and
    # handles reconnecting.
    # Other loop*() functions are available that give a threaded interface and a
    # manual interface.
    client.loop_forever()

