# Hand Gesture Controller (Beta)

## Dependencies

### Python packages

Install in the backend environment:

```bash
pip install mediapipe opencv-python-headless
```

### System packages

- Linux: `libgl1-mesa-glx`, `libglib2.0-0`
- macOS: `opencv` (for example with Homebrew)
- Windows: current OpenCV runtime and webcam drivers

### Frontend package

The UI uses native browser APIs (`getUserMedia`, `WebSocket`, `Canvas`) and does not require an additional npm package for gesture rendering.

## Environment variables

- `ENABLE_GESTURE_CONTROL=true` to expose the feature flag in settings
- `HAND_TRACKING_FPS` (optional, default controlled in frontend loop)
- `MEDIAPIPE_CONFIDENCE` (optional, default `0.7`)

## Minimum hardware

- Webcam: 720p recommended
- CPU: quad-core recommended
- RAM: 4 GB minimum

## Browser compatibility

- Chrome 87+
- Firefox 94+
- Safari 15+
- Edge 87+

Requires:

- `getUserMedia`
- `WebSocket`
- `CanvasRenderingContext2D`

## Gestures

- `pinch`: select and drag node
- `v_sign`: zoom in
- `closing_v`: zoom out
- `fist`: deselect
- `palm_forward`: pause/resume gesture command processing

## Demo mode

Enable the `Demo` toggle in the gesture panel to show the current recognized gesture overlay during tracking.

## Troubleshooting

### Webcam not found

- Check camera connection and OS permissions.
- Confirm no other app is locking the device.

### Permission denied

- Grant camera permission in browser site settings.
- Reload the page after allowing access.

### WebSocket errors

- Ensure backend is running and reachable from the frontend origin.
- Verify the `ws://<host>/ws/hand-tracking` endpoint is available.

### Low performance

- Keep the graph view in 2D mode when possible.
- Use `Tracking-only` mode to reduce rendering load.
- Close other high-CPU applications.

## Performance notes

- Input frames are capped at up to `640x480` in normal mode.
- The controller degrades to tracking-only mode on low FPS.
- Payload size is limited to 1 MB per frame on backend WebSocket.

