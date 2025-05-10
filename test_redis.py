import redis

# Connect to Redis using Upstash credentials
r = redis.Redis(
    host='adjusted-flamingo-28837.upstash.io',
    port=6379,
    password='AXClAAIjcDFjMTc3MjgyODI4YjQ0YTRmOGExMTg4MDEzMjdmNzAxNXAxMA',
    ssl=True
)

# Test setting and getting a key
r.set('foo', 'bar')
print(r.get('foo'))