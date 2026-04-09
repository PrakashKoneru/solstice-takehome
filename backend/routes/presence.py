from flask_socketio import join_room, leave_room
from extensions import socketio

# Ephemeral in-memory presence store
# { session_id: { socket_sid: { user_id, display_name, editing_slide } } }
_presence: dict[int, dict[str, dict]] = {}


def _room(session_id: int) -> str:
    return f'session:{session_id}'


def _broadcast_users(session_id: int):
    room = _room(session_id)
    # Dedupe by user_id — a single user may have multiple socket sids due to
    # reconnects, StrictMode double-mount, or hot reload. Prefer the entry
    # that's actively editing a slide (if any).
    by_user: dict[str, dict] = {}
    for info in _presence.get(session_id, {}).values():
        uid = info['user_id']
        existing = by_user.get(uid)
        if existing is None or (existing.get('editing_slide') is None and info.get('editing_slide') is not None):
            by_user[uid] = info
    users = [
        {'user_id': info['user_id'], 'display_name': info['display_name'], 'editing_slide': info.get('editing_slide')}
        for info in by_user.values()
    ]
    socketio.emit('presence:users_changed', {'session_id': session_id, 'users': users}, room=room)


@socketio.on('join_session')
def handle_join(data):
    from flask import request
    sid = request.sid
    session_id = int(data['session_id'])
    user_id = data['user_id']
    display_name = data['display_name']

    join_room(_room(session_id))
    _presence.setdefault(session_id, {})[sid] = {
        'user_id': user_id,
        'display_name': display_name,
        'editing_slide': None,
        'session_id': session_id,
    }
    _broadcast_users(session_id)


@socketio.on('leave_session')
def handle_leave(data):
    from flask import request
    sid = request.sid
    session_id = int(data['session_id'])

    leave_room(_room(session_id))
    _presence.get(session_id, {}).pop(sid, None)
    if session_id in _presence and not _presence[session_id]:
        del _presence[session_id]
    _broadcast_users(session_id)


@socketio.on('disconnect')
def handle_disconnect():
    from flask import request
    sid = request.sid
    # Clean up all sessions this socket was in
    for session_id in list(_presence.keys()):
        if sid in _presence[session_id]:
            leave_room(_room(session_id))
            del _presence[session_id][sid]
            if not _presence[session_id]:
                del _presence[session_id]
            _broadcast_users(session_id)


@socketio.on('presence:start_editing')
def handle_start_editing(data):
    from flask import request
    sid = request.sid
    session_id = int(data['session_id'])
    slide_index = data['slide_index']

    session_presence = _presence.get(session_id, {})
    if sid in session_presence:
        session_presence[sid]['editing_slide'] = slide_index
        info = session_presence[sid]
        socketio.emit('presence:editing_changed', {
            'session_id': session_id,
            'user_id': info['user_id'],
            'display_name': info['display_name'],
            'slide_index': slide_index,
        }, room=_room(session_id))
        _broadcast_users(session_id)


@socketio.on('presence:stop_editing')
def handle_stop_editing(data):
    from flask import request
    sid = request.sid
    session_id = int(data['session_id'])

    session_presence = _presence.get(session_id, {})
    if sid in session_presence:
        info = session_presence[sid]
        session_presence[sid]['editing_slide'] = None
        socketio.emit('presence:editing_changed', {
            'session_id': session_id,
            'user_id': info['user_id'],
            'display_name': info['display_name'],
            'slide_index': None,
        }, room=_room(session_id))
        _broadcast_users(session_id)


@socketio.on('presence:cursor_moved')
def handle_cursor_moved(data):
    from flask import request
    sid = request.sid
    session_id = int(data['session_id'])
    info = _presence.get(session_id, {}).get(sid)
    if not info:
        return
    socketio.emit('presence:cursor_moved', {
        'session_id': session_id,
        'user_id': info['user_id'],
        'display_name': info['display_name'],
        'x': data['x'],
        'y': data['y'],
        'slide_index': data.get('slide_index'),
    }, room=_room(session_id), skip_sid=sid)


@socketio.on('presence:slide_saved')
def handle_slide_saved(data):
    from flask import request
    sid = request.sid
    session_id = int(data['session_id'])
    slide_index = data['slide_index']
    html = data['html']

    user_id = _presence.get(session_id, {}).get(sid, {}).get('user_id')
    socketio.emit('presence:slide_updated', {
        'session_id': session_id,
        'slide_index': slide_index,
        'html': html,
        'user_id': user_id,
    }, room=_room(session_id), skip_sid=sid)
