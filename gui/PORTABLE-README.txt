XID WALLET for Windows - portable test build @VERSION@
=====================================================

This folder runs from a USB stick on 64-bit Windows 10 or 11. Nothing is installed.

THIS IS A TEST BUILD. Try it with a NEW test wallet and small amounts first.


START
-----
1. Copy the whole "XID Wallet" folder to the USB stick, or straight to the PC.
   Keep everything inside the folder together.
2. Double-click "XID Wallet.cmd".
3. Windows may warn that the file comes from the internet or an unknown publisher.
   This build is not code-signed yet. Choose "More info", then "Run anyway".

If the window does not open, double-click "XID Wallet (debug).cmd" instead.
It shows any error in a black window. Send a photo of that window.


WHAT IT NEEDS
-------------
- Windows 10 or 11, 64-bit.
- Microsoft Edge WebView2. Windows 11 has it. If Windows 10 lacks it, install
  the "Evergreen Runtime" from Microsoft's WebView2 page.
- Internet access, for balances and sending (through superknet.com).
- For card wallets: a USB PC/SC card reader (for example ACS ACR1252U) and an
  NTAG 424 DNA card.


WHERE YOUR WALLET IS KEPT
-------------------------
The wallet file is NOT on the USB stick. It is kept on the PC, in:
    C:\Users\<you>\.xcoin\
That is the same folder the command-line wallet uses. Back up the file from the
app's Settings, and keep your written seed safe.


CARD WALLETS (NTAG 424 DNA)
---------------------------
- Plug in the reader and place a blank card on it before you press "Write the card".
- Cards are made RESETTABLE unless you tick "Seal permanently". Leave it off while
  testing, so you can reset the card and use it again.
- Unlocking and every send need the card on the reader.
- Resetting a card makes its wallet unopenable. Only reset test cards holding no XID.


SAFETY
------
- The XID identity shown in the app is key number 100,000,000 (index 99,999,999).
  It is a public name. Nothing can be paid to it, and it cannot be traced to your
  balance: your funds are on index 0.
- At every start, the signing tool replays the chain's test vectors. If they fail,
  the app refuses to open a wallet.
- Check the zip's SHA-256 against the .sha256 file published beside it.
