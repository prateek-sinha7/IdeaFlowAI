function stripAttachmentMarker(text, filename) {
  let removed = false;
  return text
    .replace(/(\n\n)?\[Attached: ([^\]]*)\]/g, (match, sep, names) => {
      if (removed) return match;
      const remaining = names.split(", ");
      const at = remaining.indexOf(filename);
      if (at === -1) return match;
      removed = true;
      remaining.splice(at, 1);
      return remaining.length ? `${sep ?? ""}[Attached: ${remaining.join(", ")}]` : "";
    })
    .trim();
}
for (const n of ["my].txt","file, more.txt","a, b].txt"]) console.log(JSON.stringify(n),"=>",JSON.stringify(stripAttachmentMarker("idea\n\n[Attached: "+n+"]",n)));
