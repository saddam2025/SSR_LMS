from .tasks import run_worker

def noop(payload):
    print('processed task',payload,flush=True)

if __name__=='__main__':
    run_worker({'noop':noop})
