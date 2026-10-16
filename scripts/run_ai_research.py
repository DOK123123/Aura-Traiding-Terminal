"""The old monolithic exporter is retired. Use the isolated persistent runner."""

def main(argv=None):
    print('MONOLITHIC_EXPORT_DISABLED: use python -m scripts.research_runner init/enqueue/run with external durable --state-dir and --isolated-host.')
    return 2

if __name__=='__main__':raise SystemExit(main())
