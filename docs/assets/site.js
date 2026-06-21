(() => {
  const repo = "MathieuLF/employeurd-coda-megagest";
  const apiUrl = `https://api.github.com/repos/${repo}/releases?per_page=20`;
  const releasesUrl = `https://github.com/${repo}/releases`;
  const card = document.querySelector("[data-release-card]");

  if (!card) {
    return;
  }

  const title = document.querySelector("#release-title");
  const summary = card.querySelector("[data-release-summary]");
  const details = card.querySelector("[data-release-details]");
  const packageTarget = card.querySelector("[data-release-package]");
  const shaTarget = card.querySelector("[data-release-sha]");
  const verificationTarget = card.querySelector("[data-release-verification]");
  const primaryDownloadLink = document.querySelector("[data-primary-download]");
  const virusTotalLink = card.querySelector("[data-release-virustotal]");
  const releasePageLink = card.querySelector("[data-release-page]");
  const note = card.querySelector("[data-release-note]");

  const setText = (element, value) => {
    if (element) {
      element.textContent = value;
    }
  };

  const setHidden = (element, hidden) => {
    if (element) {
      element.hidden = hidden;
    }
  };

  const setUnavailable = (heading, message, noteText) => {
    setText(title, heading);
    setText(summary, message);
    if (details) {
      details.hidden = true;
    }
    if (primaryDownloadLink) {
      primaryDownloadLink.href = releasesUrl;
    }
    if (virusTotalLink) {
      virusTotalLink.hidden = true;
      virusTotalLink.href = releasesUrl;
    }
    if (releasePageLink) {
      releasePageLink.href = releasesUrl;
    }
    if (note) {
      note.hidden = false;
    }
    setText(note, noteText);
  };

  const findAsset = (assets, pattern, rejectPattern = null) =>
    assets.find((asset) => {
      const name = asset.name || "";
      return pattern.test(name) && (!rejectPattern || !rejectPattern.test(name));
    });

  const findPackage = (assets) =>
    findAsset(assets, /^EmployeurD-MegaGest-v[^/\\]+-portable\.zip$/i);

  const findSha = (assets, packageName) => {
    if (packageName) {
      const escaped = packageName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const directMatch = findAsset(assets, new RegExp(`${escaped}\\.sha256$`, "i"));
      if (directMatch) {
        return directMatch;
      }
    }
    return findAsset(assets, /\.sha256$/i);
  };

  const findVirusTotal = (assets) => findAsset(assets, /virustotal.*\.md$/i);

  const githubBlobUrl = (branch, path) => {
    const encodedBranch = encodeURIComponent(branch);
    const encodedPath = path.split("/").map(encodeURIComponent).join("/");
    return `https://github.com/${repo}/blob/${encodedBranch}/${encodedPath}`;
  };

  const publicVirusTotalReportUrl = (asset) =>
    asset && asset.name ? githubBlobUrl("main", `docs/releases/${asset.name}`) : releasesUrl;

  const shaFromAssetDigest = (asset) => {
    const digest = asset && asset.digest ? String(asset.digest) : "";
    const match = digest.match(/sha256:([a-f0-9]{64})/i);
    return match ? match[1].toUpperCase() : "";
  };

  const shaFromFile = async (asset) => {
    if (!asset || !asset.browser_download_url) {
      return "";
    }
    try {
      const response = await fetch(asset.browser_download_url, { cache: "no-store" });
      if (!response.ok) {
        return "";
      }
      const text = await response.text();
      const match = text.match(/[a-f0-9]{64}/i);
      return match ? match[0].toUpperCase() : "";
    } catch (_error) {
      return "";
    }
  };

  const hydrate = async () => {
    let response;
    try {
      response = await fetch(apiUrl, {
        headers: { Accept: "application/vnd.github+json" },
        cache: "no-store",
      });
    } catch (_error) {
      setUnavailable(
        "Version non vérifiée",
        "Impossible de joindre GitHub Releases pour le moment.",
        "Réessayez plus tard ou consultez directement GitHub."
      );
      return;
    }

    if (!response.ok) {
      setUnavailable(
        "Version non vérifiée",
        "GitHub Releases n'a pas répondu correctement.",
        "Consultez directement GitHub pour vérifier les fichiers disponibles."
      );
      return;
    }

    const releases = await response.json();
    const release = Array.isArray(releases)
      ? releases.find((item) => !item.draft && !item.prerelease)
      : null;

    if (!release) {
      setUnavailable(
        "Aucune version publiée",
        "La première mise en ligne officielle n'est pas encore publiée.",
        "Le téléchargement apparaîtra ici dès qu'une mise en ligne sera créée."
      );
      return;
    }

    const assets = Array.isArray(release.assets) ? release.assets : [];
    const packageAsset = findPackage(assets);
    const shaAsset = packageAsset ? findSha(assets, packageAsset.name) : null;
    const virusTotalAsset = findVirusTotal(assets);
    const releaseUrl = release.html_url || releasesUrl;
    const published = release.published_at ? new Date(release.published_at) : null;
    const publishedText = published
      ? published.toLocaleDateString("fr-CA", { year: "numeric", month: "long", day: "numeric" })
      : "date non publiée";

    setText(title, release.name || release.tag_name || "Version publiée");
    setText(summary, `Mise en ligne officielle publiée le ${publishedText}.`);
    if (details) {
      details.hidden = false;
    }
    if (releasePageLink) {
      releasePageLink.href = releaseUrl;
    }

    if (packageAsset) {
      setText(packageTarget, packageAsset.name);
      if (primaryDownloadLink) {
        primaryDownloadLink.href = packageAsset.browser_download_url;
      }
    } else {
      setText(packageTarget, "Aucun ZIP portable disponible pour cette version.");
      if (primaryDownloadLink) {
        primaryDownloadLink.href = releaseUrl;
      }
    }

    const shaValue = shaFromAssetDigest(packageAsset) || await shaFromFile(shaAsset);
    setText(shaTarget, shaValue || "Non publiée avec cette mise en ligne.");

    if (virusTotalAsset) {
      setText(verificationTarget, "");
      setHidden(verificationTarget, true);
      if (virusTotalLink) {
        virusTotalLink.href = publicVirusTotalReportUrl(virusTotalAsset);
        virusTotalLink.textContent = "Rapport VirusTotal";
        virusTotalLink.hidden = false;
      }
    } else {
      setHidden(verificationTarget, false);
      setText(verificationTarget, "Rapport VirusTotal non joint à cette mise en ligne.");
      if (virusTotalLink) {
        virusTotalLink.hidden = true;
      }
    }

    if (releasePageLink) {
      releasePageLink.textContent = "Toutes les versions";
    }

    if (note) {
      note.hidden = true;
    }
  };

  hydrate();
})();
