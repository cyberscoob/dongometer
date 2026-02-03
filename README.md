# The Dongometer 🍆

Real-time chaos metrics dashboard for the CClub donghouse.

## Features

- **Chaos Score**: 0-100 calculated from multiple factors
- **Chat Velocity**: Messages per minute/hour tracking
- **Door Events**: Open/close monitoring
- **Pizza Counter**: Essential sustenance tracking
- **Real-time Updates**: Auto-refreshes every 5 seconds
- **Historical Data**: SQLite backend for trend analysis

## Chaos Scale

| Score | Level | Description |
|-------|-------|-------------|
| 0-20 | 😴 Calm | The donghouse sleeps |
| 21-40 | ⚡ Active | Normal operations |
| 41-60 | 🍕 Chaotic | Pizza's here, someone's compiling |
| 61-80 | 👿 Demonic | Hardin needs a grader, Yakko is down |
| 81-100 | ☠️ Apocalyptic | Gigglesgate 2.0, run |
| **42069+** | 🌿 **Fenthouse** | *Folding in the Fenthouse* — Maximum chaos, admin override, rainbow mode |

## Installation

```bash
pip install -r requirements.txt
python app.py
```

## API Endpoints

- `GET /` - Dashboard
- `GET /api/metrics` - Current metrics JSON
- `POST /api/event` - Record new event
- `GET /api/history?hours=24` - Historical data
- `GET /api/leaderboard` - Top chaos hours

## Event Types

```json
{
  "type": "chat_message",
  "value": 1,
  "details": "optional description"
}
```

Types: `chat_message`, `door_open`, `door_close`, `pizza`, `reset_pizza`

## Future Integrations

- Matrix bot for auto chat counting
- Door sensor webhook
- Pizza button (physical or chat command)
- LED strip chaos level indicator
- Discord/Matrix bot commands

## Port

Default: 5000

Shaggy will help expose it properly. 🚀

## Deploy / Restart (inside doghouse)

This project runs **inside the Scoob doghouse container**.
Pushing to git does **not** automatically restart the running server.

After you change code (and/or run git pull inside the container), restart dongometer with:

    /home/scoob/dongometer/dongometerctl restart

Check status/logs:

    /home/scoob/dongometer/dongometerctl status
    # logs: /home/scoob/dongometer/dongometer_app.log

Note: This container does not run systemd; dongometerctl is the service manager.
