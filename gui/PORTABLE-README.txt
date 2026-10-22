XID WALLET for Windows - portable test build @VERSION@
=====================================================

Download the zip, extract it, double-click "XID Wallet.exe". Nothing is installed.
It also runs from a USB stick.

THIS IS A TEST BUILD. Try it with a NEW test wallet and small amounts first.


START
-----
1. Extract the zip: right-click it, choose "Extract All", then "Extract".
   (Opening the exe from inside the zip does not work.)
2. Open the extracted "XID Wallet" folder and double-click "XID Wallet.exe"
   (the one with the xCoin logo).
3. The first time, Windows may say "Windows protected your PC", because this
   build is not code-signed yet. Choose "More info", then "Run anyway".
4. Optional: in the wallet, Settings, Shortcuts, press "Add to desktop and
   Start menu" to get an XID Wallet icon there. You can also right-click
   XID Wallet.exe and choose "Pin to Start" or "Pin to taskbar".

Keep everything inside the folder together: XID Wallet.exe needs the runtime
and app folders beside it. Move the whole folder wherever you like. For a PC,
a good home is
    C:\Users\<you>\AppData\Local\Programs\XID Wallet
which is where Windows keeps per-user apps.

If the window does not open, open the "app" folder and double-click
"XID Wallet (debug).cmd". It shows any error in a black window. Send a photo
of that window.


CHECK THE DOWNLOAD
------------------
The SHA-256 of the zip is published beside it (the .sha256 file, and the
README of the GitHub repository). To check it, open PowerShell where the zip
is and run:
    Get-FileHash .\XID-Wallet-Windows-portable-@VERSION@.zip
The Hash it prints must match the published one exactly.


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
