# Installation
If you are interested in this plugin only:  
<a href="https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FKastB%2Faddon-tesla-pv-charging" target="_blank"><img src="https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg" alt="Open your Home Assistant instance and show the add add-on repository dialog with a specific repository URL pre-filled."></a>  
Or here if you need the vzlogger plugin as well:  
<a href="https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FKastB%2Fhassio-addons" target="_blank"><img src="https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg" alt="Open your Home Assistant instance and show the add add-on repository dialog with a specific repository URL pre-filled."></a>  

<a href="https://my.home-assistant.io/redirect/supervisor_addon/?addon=958e2f13_teslapvcharging" target="_blank"><img src="https://my.home-assistant.io/badges/supervisor_addon.svg" alt="Open your Home Assistant instance and show the dashboard of a Supervisor add-on."></a>

# Description
Plugin for pv excess charging.  
The basic python script that controls the charge speed via the tesla api and gets its information via mqtt (teslamate streaming api to reduce the api calls, vzlogger for the grid consumption from the smart-meter) is well tested, the changes done for this plugin not yet.
Feel free to create issues / fork, change and create merge-requests.

# Properties
The step-size for 400V is ~690W (230V*3*1A) unless you use less than 3 phases.  
There is a control loop which:  
- stops charging below a certain amperage (the car has 500W consumption, and it becomes too inefficient to charge with low charge speeds => stop charging and go to sleep during night)
- charges as fast as possible below a certain SOC (configurable)
- tries to prevent feed-in below a certain SOC (configurable)
- tries to prevent grid consumption above a certain SOC (configurable)
- does not change settings if max-SOC is 100% or max-charge-speed is higher than a certain speed (due to delays you should first set the do-not-interfere SOC in your app, and change it back later if you wish) => you can control the behaviour with the Tesla app, when you go on a trip.
Caveats:
- The mqtt topics are not yet configurable (feel free to fork and create a merge request, or create an issue with a feature request)
- some parameters might not yet be exposed in the plugin (e.g. effective voltage (just 2 phases, US-grid), ?)
- This works only for Teslas, we must rely on an unofficial api, and at the moment only for one car (might change soon though)
- I limited the rate to 30s and the car needs a few seconds to adapt the charge speed. So we consume 700-1000W in the "prevent-feed-in-phase": at 1PM the Tesla was plugged in:
![image](https://user-images.githubusercontent.com/9568700/163136293-c49f7e08-d66a-470c-9d55-408dabdfffcf.png)
