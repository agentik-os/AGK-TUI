export const ORGANISATIONS = [
  {
    id: "operator",
    label: "Operator",
    description: "Infrastructure et opérations",
    port: 8460,
    path: "/operator/",
    accent: "#8fffc1",
  },
  {
    id: "agentik",
    label: "Agentik",
    description: "Organisation et produits",
    port: 8461,
    path: "/agentik/",
    accent: "#84b7ff",
  },
  {
    id: "mission",
    label: "Mission",
    description: "Missions et espaces clients",
    port: 8462,
    path: "/mission/",
    accent: "#c9a6ff",
  },
  {
    id: "private",
    label: "Private",
    description: "Espace personnel isolé",
    port: 8463,
    path: "/private/",
    accent: "#ffb98f",
  },
] as const;

export type Organisation = (typeof ORGANISATIONS)[number];
export type OrganisationId = Organisation["id"];

export const DEFAULT_ORGANISATION: OrganisationId = "operator";
export const STORAGE_KEY = "agk.hermes-fleet.organisation";

export function isOrganisationId(value: string | null): value is OrganisationId {
  return ORGANISATIONS.some((organisation) => organisation.id === value);
}

export function resolveOrganisationId(
  search: string,
  storedValue: string | null,
): OrganisationId {
  const queryValue = new URLSearchParams(search).get("org");

  if (isOrganisationId(queryValue)) {
    return queryValue;
  }

  if (isOrganisationId(storedValue)) {
    return storedValue;
  }

  return DEFAULT_ORGANISATION;
}

export function getOrganisation(id: OrganisationId): Organisation {
  const organisation = ORGANISATIONS.find((candidate) => candidate.id === id);

  if (!organisation) {
    throw new Error(`Unknown organisation: ${id}`);
  }

  return organisation;
}

export function dashboardPath(id: OrganisationId): string {
  return getOrganisation(id).path;
}

export function withOrganisation(search: string, id: OrganisationId): string {
  const params = new URLSearchParams(search);
  params.set("org", id);
  const query = params.toString();
  return query ? `?${query}` : "";
}
