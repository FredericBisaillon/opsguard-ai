export default function Home() {
  return (
    <main className="min-h-screen bg-zinc-50 px-6 py-16 text-zinc-950">
      <section className="mx-auto flex min-h-[calc(100vh-8rem)] max-w-4xl flex-col justify-center">
        <p className="text-sm font-medium uppercase tracking-wider text-emerald-700">
          Secure AI Document Review Platform
        </p>

        <h1 className="mt-4 text-4xl font-semibold sm:text-5xl">
          OpsGuard AI
        </h1>

        <p className="mt-5 max-w-2xl text-lg leading-8 text-zinc-700">
          A secure, testable platform for reviewing documents with applied AI,
          built step by step.
        </p>

        <div className="mt-10 max-w-md rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
          <p className="text-sm font-medium text-zinc-500">Backend status</p>

          <div className="mt-3 flex items-center gap-3 text-zinc-800">
            <span
              className="h-2.5 w-2.5 rounded-full bg-amber-500"
              aria-hidden="true"
            />
            <span>Not connected yet</span>
          </div>
        </div>
      </section>
    </main>
  );
}
