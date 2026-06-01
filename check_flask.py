import flask
print('flask file:', flask.__file__)
print('flask version:', getattr(flask, '__version__', 'unknown'))
print('has before_first_request:', hasattr(flask.Flask, 'before_first_request'))
print('methods:', [m for m in dir(flask.Flask) if 'before' in m])
