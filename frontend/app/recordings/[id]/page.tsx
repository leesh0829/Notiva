interface Props {
  params: Promise<{ id: string }>;
}

export default async function RecordingDetailPage({ params }: Props) {
  const { id } = await params;

  return (
    <main className="p-6 space-y-4">
      <h1 className="text-2xl font-bold">Recording {id}</h1>
      <section>
        <h2 className="font-semibold">요약</h2>
      </section>
      <section>
        <h2 className="font-semibold">원문</h2>
      </section>
      <section>
        <h2 className="font-semibold">Q&A</h2>
      </section>
    </main>
  );
}
