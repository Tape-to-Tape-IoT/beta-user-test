# Beta challenge

Thanks for applying! This takes about an hour. Searching the web is allowed and expected.

**You need:** a Raspberry Pi running Raspberry Pi OS with internet access, a GitHub account,
and the personal API key we sent you. Work over SSH or with a keyboard and screen, your choice.

**Never post your API key anywhere**, including in your issue.

## Steps

1. Clone this repository into `~/app` on your Pi:

   ```bash
   git clone https://github.com/Tape-to-Tape-IoT/beta-user-test.git ~/app
   ```

   If `git` is missing, install it first with `sudo apt install git`.
2. Create a Python virtual environment in `~/app` and install the dependencies into it
   (recent Raspberry Pi OS versions block system-wide `pip install`):

   ```bash
   cd ~/app
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

   If `python3 -m venv` fails, install it first with `sudo apt install python3-venv`.
   The venv's Python is `~/app/venv/bin/python3`; `source venv/bin/activate` makes `python3`
   point to it in your current SSH session only.
3. Create your own config from the example:

   ```bash
   cd ~/app
   cp config.example.toml config.toml
   ```

   Then edit `config.toml` from the command line (for example `nano config.toml`) and fill in:
   - `api_key`: the key we sent you
   - `discord_username`: your Discord username
   - `pi_model`: your Raspberry Pi model
   - `display_cols` and `display_rows`: your display size
   - `nhl_team`: your favorite NHL team's abbreviation (e.g. MTL)
4. Run the app once by hand with `python3 app.py` from `~/app`, with the venv activated.
   Read what it prints, fix anything it complains about, then stop it with Ctrl+C.
5. Install supervisor and create a program named `app` that:
   - runs the app as your user, from `~/app`, with the venv's Python
   - starts automatically when the Pi boots
   - restarts whenever the app process stops
   - writes all its output to `/var/log/app/app.log`

   Install supervisor and make sure it starts on boot:

   ```bash
   sudo apt update
   sudo apt install -y supervisor
   sudo systemctl enable --now supervisor
   ```

   Create the log directory. Supervisor won't create it, and the program fails to start
   without it:

   ```bash
   sudo mkdir -p /var/log/app
   ```

   Create the program file with `sudo nano /etc/supervisor/conf.d/app.conf`. Replace `pi`
   with your own username (run `whoami`) in all four places:

   ```ini
   [program:app]
   command=/home/pi/app/venv/bin/python3 app.py
   directory=/home/pi/app
   user=pi
   environment=HOME="/home/pi"
   autostart=true
   autorestart=true
   stdout_logfile=/var/log/app/app.log
   redirect_stderr=true
   ```

   - `autorestart=true` is required. The app exits with code 0 on a clean stop, and
     supervisor's default setting doesn't restart a program that exits with code 0.
   - `redirect_stderr=true` sends error output to the same log file.
   - Paths must be absolute. Supervisor doesn't expand `~`.

   Load the program:

   ```bash
   sudo supervisorctl reread
   sudo supervisorctl update
   ```

   `sudo supervisorctl status app` should say `RUNNING`. If it says `FATAL` or `BACKOFF`,
   run `sudo supervisorctl tail app` and `sudo tail /var/log/supervisor/supervisord.log`
   to see why.
6. Check that `curl localhost:8081/health` returns `ok`.
7. Prove it recovers:
   - Find the app's process ID and `kill` it, then confirm it comes back:

     ```bash
     sudo supervisorctl pid app
     kill <pid>
     sudo supervisorctl status app
     ```

     Replace `<pid>` with the number the first command printed. The status should say
     `RUNNING` again, with a different pid and an uptime of a few seconds.
   - Reboot the Pi, then confirm it comes back:

     ```bash
     sudo reboot
     ```

     Your SSH session will drop. Once the Pi is back up, reconnect and run:

     ```bash
     sudo supervisorctl status app
     curl localhost:8081/health
     ```
8. Download your profile card from your browser:
   - Find the Pi's IP address:

     ```bash
     hostname -I
     ```

     Use the first address it prints (for example `192.168.1.42`).
   - Open `http://<pi-address>:8081` in your browser, replacing `<pi-address>` with that
     address, and click **Download profile card**.

   If you set a hostname when you installed Raspberry Pi OS, you can use it instead of the
   IP address, for example `http://raspberrypi.local:8081`.
9. Open an issue in this repo using the **Beta application** form.
   Attach your profile card. Then run the command below and paste its output into the
   **Supervisord log** field:

   ```bash
   sudo tail /var/log/supervisor/supervisord.log
   ```

## Done when

- [ ] Your issue shows your profile card
- [ ] Your supervisord log shows `app` entering the `RUNNING` state after the reboot
- [ ] No API key appears anywhere in your issue

## Cleaning up (optional)

Once your issue is submitted you can remove everything the challenge put on your Pi.
Save a copy of your profile card first if you want to keep it.

1. Stop the app:

   ```bash
   sudo supervisorctl stop app
   ```

2. Delete the supervisor config file you created for it, then tell supervisor to forget
   the program. The path below is the usual place; use your own if you put it elsewhere.

   ```bash
   sudo rm /etc/supervisor/conf.d/app.conf
   sudo supervisorctl reread
   sudo supervisorctl update
   ```

   `sudo supervisorctl status` should no longer list `app`.

3. Delete the app (this also removes the venv and your `config.toml` with the API key)
   and its logs:

   ```bash
   rm -rf ~/app
   sudo rm -rf /var/log/app
   ```

4. If you installed supervisor only for this challenge, uninstall it:

   ```bash
   sudo apt purge supervisor
   sudo apt autoremove
   ```

   Skip this step if anything else on your Pi runs under supervisor.

To check, `curl localhost:8081/health` should now fail to connect.
