export const REPO_URL = "https://github.com/lgm1007/it-job-description-collector";

/** The copyright notice, linking to the source on GitHub. */
export default function Copyright({ className }: { className?: string }) {
  return (
    <a className={className} href={REPO_URL} target="_blank" rel="noopener noreferrer" title="GitHub 저장소">
      © 2026 lgm1007 · GitHub
    </a>
  );
}
