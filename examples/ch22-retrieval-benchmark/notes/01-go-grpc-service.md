# Go Service Notes

I used Go to build internal gRPC services where latency mattered more than framework ergonomics.

The useful lesson was not just "Go is fast". It was that the language made it easier to keep concurrency behavior obvious under load, especially when a service had to multiplex requests across workers.

Most of the deployment work for these services happened inside containers and later moved into Kubernetes.

