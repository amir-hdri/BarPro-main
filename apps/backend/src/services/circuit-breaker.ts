export class CircuitBreakerOpenError extends Error {}

export class CircuitBreaker {
  private failures = 0;
  private openedAt: number | null = null;

  public constructor(
    private readonly failureThreshold: number,
    private readonly resetTimeoutMs: number
  ) {}

  public async execute<T>(operation: () => Promise<T>): Promise<T> {
    if (this.isOpen()) {
      throw new CircuitBreakerOpenError('Circuit breaker is open');
    }

    try {
      const result = await operation();
      this.failures = 0;
      this.openedAt = null;
      return result;
    } catch (error) {
      this.failures += 1;
      if (this.failures >= this.failureThreshold) {
        this.openedAt = Date.now();
      }
      throw error;
    }
  }

  public isOpen(): boolean {
    if (this.openedAt === null) {
      return false;
    }
    if (Date.now() - this.openedAt > this.resetTimeoutMs) {
      this.failures = 0;
      this.openedAt = null;
      return false;
    }
    return true;
  }
}
