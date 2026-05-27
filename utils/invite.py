import random
import string

def generate_invite_code():
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    return f'INV-{suffix}'


def validate_invite_code(db, uid, code):
    user_ref = db.collection('users').document(uid)
    user = user_ref.get().to_dict() or {}
    if user.get('invite_override'):
        return True, 'Invite requirement overridden by admin.'
    if code != (user.get('invite_code') or '').upper():
        return False, 'Invalid invite code.'
    if user.get('invite_used'):
        return False, 'Invite code already used.'
    user_ref.update({'invite_used': True})
    return True, 'Invite accepted.'
