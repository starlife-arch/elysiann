import os

def create_stripe_checkout(uid):
    base = os.getenv('APP_URL', 'http://localhost:5000')
    return f'{base}/dashboard?payment=stripe&uid={uid}'


def create_pesapal_checkout(uid):
    base = os.getenv('APP_URL', 'http://localhost:5000')
    return f'{base}/dashboard?payment=pesapal&uid={uid}'
