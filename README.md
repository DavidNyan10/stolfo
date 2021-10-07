# stolfo
music bot made after rythm and groovy's takedown<br/>i am running an instance of this publicly, invite [here](https://discord.com/api/oauth2/authorize?client_id=889928187746873344&permissions=412689493312&scope=bot)

## Features
- `play` command - takes any link **(including spotify track, album or playlist links)** or a search query to search youtube for.
    - `playnext` - same as `play` but adds to start of the queue
        - `playskip` - same as `playnext` but also skips the currently playing song
    - `playshuffle` - same as `play`, but adds the album/playlist to the queue in randomized order
- `move` command - moves a track to another position in the queue.
- `seek` command - seeks to a set position in the track (HH:MM:SS / MM:SS) or X seconds forward or back (+Xs / -Xs)
- `shuffle` command - toggles shuffle on or off. when enabled, shuffles the queue which can be restored back to normal by disabling.
- other basic commands - `queue`, `skip`, `remove`, `nowplaying`, `disconnect`

## Discord server
if you want to stay up to date on the bot's features and development (including unexpected shutdowns etc.), join the update server [here](https://discord.gg/scruTsFmZG)

## Cloning
in case you decide to clone this, i won't offer you much support. it requires a Lavalink server and all that so make sure you have that running, then change values from the code accordingly
