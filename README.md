[![HA Logo](https://scontent.fktw1-1.fna.fbcdn.net/v/t1.0-1/p200x200/13716247_293102314376608_8339330921854655254_n.jpg?_nc_cat=100&_nc_oc=AQnH7sYMCuQvmY3sulW-DORlpsbJIJTAzxHJWx8QwSnngdBRlBf8SS3ZF2K7VBhVoIw&_nc_ht=scontent.fktw1-1.fna&oh=6214dc5c17f7ede8c5b0ece345627bb3&oe=5E8CD2CE)](https://www.forumextalife.pl/)

[![ExtaLife Logo](https://extalife.pl/wp-content/themes/wi/images/logo.png)](https://www.forumextalife.pl/) 

ZAMEL Exta Life integration with Home Assistant based on custom component.
### Supported devices
* Switches: ROP-21, ROP-22, ROM-24
* Dimmers: RDP-21
* LED controllers: SLR-21, SLR-22
* Smart sockets: ROG-21
* Roller blind controllers: SRP-22, SRM-22
* Heating controller: RGT-01, GKN-01
* Sensors: RCT-21, RCT-22, RNK-21&RNK-22 build-in temperature sensor, flood sensor RCZ-21, motion sensor RCR-21, window sensor RCK-21, multisensor RCM-21

**Note:**: Certain switches are mapped into Home Asistant life entities depending on icon assigned to them. This is to support voice control by Google Assistant and others and because switches are mostly used for light control.
### Configuration
Edit your configuration.yaml file and add the following lines:

    extalife:
      user: <user>
      password: <password>
      poll_interval: 5
The 'poll_inteval' parameter is optional. The default value for it is 5 minutes

Discussion, news and many more on https://www.forumextalife.pl/


