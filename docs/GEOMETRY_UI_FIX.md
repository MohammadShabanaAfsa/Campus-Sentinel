# Camera Geometry UI repair — 13 October 2026

## Root cause

The previous editor left an empty canvas mounted when its authenticated snapshot
request failed. Missing/expired-session failures were treated like ordinary
frame failures, so the editor did not explain that sign-in was required. The
image preload also lacked an error handler for undecodable images. Drawing was
not gated by a successful image load. Clicking a mode tab stopped drawing until
the separate Draw action was clicked, without clearly communicating that state.

An expired session therefore can cause the blank frame: authenticated snapshot
requests reject invalid tokens with HTTP 401. The reported session-expired
message is consistent with this path, but the user's browser token was not
inspected. It is not the only possible cause: the native check found Classroom
returns HTTP 404 because it has no current frame. General Entrance returned a
readable 640×480 JPEG with a valid token.

## Change

The frontend editor now displays the camera JPEG in an image element and a
transparent, reactive SVG layer immediately above it. The parent uses the actual
decoded frame aspect ratio; the SVG uses the same natural width/height and fills
that parent with absolute positioning, z-index 10 and explicit pointer handling.
There is no canvas painting lifecycle or image ref timing dependency.

Every click appends normalized x/y values based on the displayed SVG rectangle.
Markers, line segments and polygons render directly from React state. Point one
shows a marker; point two adds a line; three or more points form a closed polygon.
Vehicle mode accepts exactly two points and shows its line immediately. A valid
loaded frame activates drawing in the selected mode; changing modes also
activates drawing. Draw/Save/Edit/Clear/Redraw/Cancel remain available.

The editor checks the existing session token, listens to the existing session
expiry event, handles HTTP 401, and clears the image/draft on expiry. It shows
**Please sign in again** with a sign-in link. It does not refresh credentials or
pretend the user is authenticated. After sign-in, reopening the editor loads a
new authenticated snapshot.

Missing, failed or undecodable frames show **Camera frame unavailable** with a
Retry Frame action. Drawing and saving remain disabled until the image decodes
successfully. No empty drawing surface remains visible as a substitute for a
failed frame. Clear can still remove saved geometry when signed in.

## Verification

- **35 frontend tests passed**, including nine focused geometry tests.
- Tests verify frame loading and SVG dimensions/positioning, immediate markers,
  polygon closure, two-click counting line, normalized Save, Edit, Clear, Cancel,
  immediate mode drawing, missing session, HTTP 401, session expiry mid-edit,
  HTTP 404 and image decoding failure.
- TypeScript checks and the production build passed.
- Native read-only API check: General Entrance snapshot HTTP 200, readable JPEG,
  640×480; Classroom snapshot HTTP 404, no frame; invalid session HTTP 401.
- Restricted Zone drawing: **yes in frontend interaction tests**.
- Vehicle Count line drawing: **yes in frontend interaction tests**.

The authenticated user browser was not manually operated during this repair.
Classroom drawing requires that camera to supply a frame. Backend detection,
camera streams, stored zones/lines and authentication logic were not modified.
Only the frontend is reloaded to serve `.next-geometry-fix`.

Files changed:

- `frontend/src/components/cameras/ZoneDrawerModal.tsx`
- `frontend/tests/camera-geometry.test.cjs`
- `frontend/tsconfig.json` (Next.js build type directory)
- `docs/GEOMETRY_UI_FIX.md`

Evidence: `logs/geometry-ui-snapshot-verification.json`.
Disposable launcher: `logs/restart-frontend-geometry-fix.sh`.
