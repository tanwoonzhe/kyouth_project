/**
 * SkillScope – API service layer
 * All HTTP calls to the frontend server are centralised here.
 */

/**
 * Submit the analysis form and return structured market-fit results.
 * @param {FormData} formData
 * @returns {Promise<Object>}
 */
export async function analyzeMarket(formData) {
  let response;
  try {
    response = await fetch('/analyze', { method: 'POST', body: formData });
  } catch {
    throw new Error('Could not reach the server. Please check your connection.');
  }

  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error('Server returned an unreadable response. Please try again.');
  }

  if (!response.ok) {
    throw new Error(data.error || `Request failed (${response.status})`);
  }

  return data;
}

/**
 * Fetch aggregate market statistics.
 * @returns {Promise<Object>}
 */
export async function getStats() {
  let response;
  try {
    response = await fetch('/api/stats');
  } catch {
    throw new Error('Could not reach the server.');
  }

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.error || `Stats unavailable (${response.status})`);
  }

  return response.json();
}

/**
 * Fetch distinct job roles for the Target Role dropdown.
 * Returns a string array; the server falls back to a preset list if the
 * backend is unavailable.
 * @returns {Promise<string[]>}
 */
export async function getRoles() {
  let response;
  try {
    response = await fetch('/api/roles');
  } catch {
    throw new Error('Could not reach the server.');
  }

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.error || `Roles unavailable (${response.status})`);
  }

  const data = await response.json();
  return data.roles ?? data;
}

/**
 * Fetch distinct locations for the Location dropdown.
 * Returns a string array; the server falls back to a preset list if the
 * backend is unavailable.
 * @returns {Promise<string[]>}
 */
export async function getLocations() {
  let response;
  try {
    response = await fetch('/api/locations');
  } catch {
    throw new Error('Could not reach the server.');
  }

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.error || `Locations unavailable (${response.status})`);
  }

  const data = await response.json();
  return data.locations ?? data;
}
