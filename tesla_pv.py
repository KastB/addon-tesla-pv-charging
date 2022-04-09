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

MAIL = os.getenv('TESLA_MAIL')
change_of_charge_power = False

with teslapy.Tesla(MAIL) as tesla:
    class HistoricData(object):
        def __init__(self):
            self.timestamp = None
            self.power_history = None
            self.car = dict()
            self.check_period_minutes = 0.5
            self.reset()

        def reset(self):
            self.power_history = list()
            self.timestamp = datetime.now()

        def add(self, topic, data):
            if "vzlogger" in topic:
                self.power_history.append(float(data.decode("ASCII")))
            elif "teslamate" in topic:
                self.car[topic.split("/")[-1]] = data.decode("ASCII")
            else:
                print(f"unknown topic: {topic} with data: {data}")

            if datetime.now() - self.timestamp > timedelta(minutes=self.check_period_minutes):
                if len(self.power_history) > 10:
                    update_charge_speed(True,
                                        self.car["plugged_in"] == "true",
                                        float(self.car["battery_level"]),
                                        float(self.car["charger_actual_current"]),
                                        float(self.car["charger_power"]),
                                        float(self.car["charge_limit_soc"]),
                                        np.array(self.power_history))
                self.reset()


    historic_data = HistoricData()


    def get_vehicle():
        TOKEN = os.getenv('TESLA_TOKEN')
        print(f"already authorized: {tesla.authorized}")
        if not tesla.authorized:
            tesla.refresh_token(refresh_token=TOKEN)
        try:
            vehicle = tesla.vehicle_list()[0]
        except:
            tesla.refresh_token(refresh_token=TOKEN)
            vehicle = tesla.vehicle_list()[0] 
        vehicle.sync_wake_up()
        return vehicle


    def set_charging(start):
        print(f"{str(datetime.now())} start charging: {start}")
        vehicle = get_vehicle()
        try:
            if start:
                vehicle.command('START_CHARGE')
            else:
                vehicle.command('STOP_CHARGE')
        except Exception as e:
            print(e)


    def set_charge_speed(amperage, do_not_interfere_amperage):
        vehicle = get_vehicle()
        vehicle.sync_wake_up()
        cur_amps = vehicle["charge_state"]["charge_current_request"]
        if cur_amps < do_not_interfere_amperage and \
                cur_amps != amperage:
            print(f"set amperage {amperage} was {cur_amps}")
            vehicle.command("CHARGING_AMPS", charging_amps=amperage)
            global change_of_charge_power
            change_of_charge_power = True
            print(f"{str(datetime.now())}: amperage set")


    def update_charge_speed(twc_is_connected: bool, car_plugged: bool, soc: float, current_amperage: float, current_charge_power: float, charge_limit_soc: float, power_history: np.array) -> object:
        empty_soc = os.getenv('EMPTY_SOC')  # soc below the car is considered empty => full charging speed
        mid_soc = os.getenv('MID_SOC')  # soc until we want to charge every bit of produced pv power
        do_not_interfere_charge_limit_soc = os.getenv('DO_NOT_INTERFERE_CHARGE_LIMIT')

        do_not_interfere_amperage = os.getenv('DO_NOT_INTERFERE_AMPERAGE')
        min_amperage = os.getenv('MIN_AMPERAGE')

        # strip first 10 seconds after power change as the charger needs to ramp up (to avoid oszillation)
        global change_of_charge_power
        if change_of_charge_power:
            print(f"strip first seconds because we lately changed the charging speed size: {len(power_history)}")
            change_of_charge_power = False
            try:
                power_history = power_history[10:]
            except:
                print(f"Power history was too short, could not strip first 10s: {len(power_history)}")

        # if we charge at home
        if twc_is_connected:
            # check if vehicle is plugged in as well
            if car_plugged:
                print(f"current_amperage: {current_amperage}")
                print(f"current_charge_limit: {charge_limit_soc}")
                if current_amperage >= do_not_interfere_amperage or \
                    charge_limit_soc >= do_not_interfere_charge_limit_soc:
                    print("do_not_interfere")
                    return
                if soc < empty_soc:
                    new_amperage = do_not_interfere_amperage - 1
                    new_do_charging = True
                else:
                    effective_voltage = os.getenv('EFFECTIVE_VOLTAGE')
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
                            print(f"Deviation too small - keeping old chargespeed min: {np.min(power_history)}")
                            return
                        new_charge_power = -np.min(consumption_history)
                        new_amperage = ceil(new_charge_power / effective_voltage)
                        print(f"Chargepower (mix): {new_charge_power} W => {new_amperage} A (mean:{np.mean(consumption_history)}; max: {np.max(consumption_history)}")
                        if new_amperage <= 0:
                            new_amperage = min_amperage
                            new_do_charging = False
                        else:
                            new_do_charging = True
                    else:
                        if abs(np.max(power_history)) < 50:        # hysteresis
                            print(f"Deviation too small - keeping old chargespeed max: {np.max(power_history)}")
                            return
                        new_charge_power = -np.max(consumption_history)
                        new_amperage = floor(new_charge_power / effective_voltage)
                        print(f"Chargepower (PV only): {new_charge_power} W => {new_amperage} A")
                        if new_amperage < min_amperage:
                            new_amperage = min_amperage
                            new_do_charging = False
                        else:
                            new_do_charging = True

                if (current_charge_power > 0.1) != new_do_charging:
                    set_charging(new_do_charging)
                if new_do_charging:
                    new_amperage = max(new_amperage, min_amperage)
                    if new_amperage != current_amperage:


    # The callback for when the client receives a CONNACK response from the server.
    def on_connect(client, userdata, flags, rc):
        print("Connected with result code " + str(rc))
        # Subscribing in on_connect() means that if we lose the connection and
        # reconnect then subscriptions will be renewed.
        client.subscribe("teslamate/teslamate/cars/1/#")
        client.subscribe("vzlogger/data/chn2/raw")


    # The callback for when a PUBLISH message is received from the server.
    def on_message(client, userdata, msg):
        global historic_data
        historic_data.add(msg.topic, msg.payload)
        # print(msg.topic + " " + str(msg.payload))


    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.username_pw_set(os.getenv('MQTT_USER'), os.getenv('MQTT_PW'))
    client.connect(os.getenv('MQTT_HOST'), os.getenv('MQTT_PORT'), 60)

    # Blocking call that processes network traffic, dispatches callbacks and
    # handles reconnecting.
    # Other loop*() functions are available that give a threaded interface and a
    # manual interface.
    client.loop_forever()

