# DogDesk (GNOME × Undertale)

A desktop pet for GNOME: the small white dog from **your own copy of Undertale** lives on your desktop.

- Trots along the tops of your windows and the bottom of the screen, and rides along when you move a window.
- Digs into the ground and pops up somewhere else now and then — and gets out of the way at once if
  you drag a window or file through it.
- Naps on whatever it's standing on when you've been away for a few minutes; wakes when you're back.
- Looks up when a notification arrives (not in Do Not Disturb), and now and then digs over to chew on
  a window you close.
- Click it to pet it. Menu in the top bar: show/hide, call it over, let it nap, chatty, sounds.
- Lives on any of your monitors; follows you to a new workspace; hides in the Activities overview.
- Stays still while you're typing or watching something (keyboard busy, pointer still), and is
  sleepier late at night. In winter a long nap turns it into a little snow pile.
- Never covers fullscreen apps or games; text boxes can be turned off; sounds are off by default.
- Light on your computer: it checks windows a few times a second and barely runs while asleep.

It's a GNOME Shell extension (GNOME 47+). Its sprites and the dog's jingle are read from your Undertale
install (Steam native/Flatpak/Snap, Linux, Windows/Proton or macOS builds; or set the data file in
the preferences); nothing from Undertale is included. Not affiliated with Toby Fox.

## Install
With Mashwright: `mashwright get dogdesk` (or **Discover → From the catalog**). By hand: copy
`dogdesk@aaronateataco.github.io` to `~/.local/share/gnome-shell/extensions/`, log out and in, and
turn it on in Extensions.

## Build
    python3 tools/build.py      # package/dogdesk-extension.zip and build/dogdesk.mashwright

`tools/gmdata.py` is a small Python reader for GameMaker 1.4 data files used while developing
(`python3 tools/gmdata.py path/to/game.unx dog` lists the dog's sprites).
