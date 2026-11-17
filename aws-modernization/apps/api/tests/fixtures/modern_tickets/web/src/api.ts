export async function createTicket(title: string, city: string) {
    const res = await fetch("/api/Tickets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, city }),
    });
    return res.json();
}

export async function getTicket(id: number) {
    return (await fetch(`/api/Tickets/${id}`)).json();
}

export async function archive(id: number) {
    await fetch(`/api/Tickets/${id}/archive`, { method: "POST" });
}
