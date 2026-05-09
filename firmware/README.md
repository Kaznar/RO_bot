# Arduino HID serial (right mouse)

The Python bridge sends **`RD`** / **`RU`** for the right button (same idea as **`MD`** / **`MU`** for the left). If your sketch answers with `ERR RD`, it knows the token but does not call `Mouse.press(MOUSE_RIGHT)` yet.

Add to your `loop()` command parser (HID-Project / `Mouse` API):

```cpp
} else if (cmd == "RD") {
  Mouse.press(MOUSE_RIGHT);
  Serial.println("OK");
} else if (cmd == "RU") {
  Mouse.release(MOUSE_RIGHT);
  Serial.println("OK");
```

Use the **same** composite USB HID device for keyboard (KD/KU) and mouse so **Alt from the board + right click from the board** is one logical input to Windows, like your physical Alt+RMB.

After flashing, reconnect USB; the bot re-probes right-click on the next session.
