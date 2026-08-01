# Security posture

## Accounts

Argon2id password hashes. Sessions are opaque random tokens stored server-side as
SHA-256 hashes, delivered in an httpOnly, SameSite=Lax cookie.

Server-side sessions rather than signed stateless tokens: a JWT cannot be revoked
without the same server-side list a plain token needs anyway, and this way signing
out actually ends the session. Only the hash is stored, so a database dump does not
hand over live sessions.

## First run

Registration is open only while no account exists. That first account becomes the
administrator and is signed in immediately, so a fresh deployment has a way in
without a bootstrap password sitting in the environment. Afterwards, accounts are
created by an administrator — an internally deployed tool with open registration is
an unlocked door.

Login answers identically for an unknown email and a wrong password, so the endpoint
cannot be used to enumerate who has an account.

## Roles

`operator` runs surveys and labels signs. `admin` also manages accounts and
basemaps. An administrator cannot disable or demote their own account: locking
yourself out of the only admin account is a support call, not a feature.

## Tenancy

Surveys belong to an organisation, not only to the person who ran them — staff
change, and the inventory a city paid for must not leave with them.

Every read is filtered through one helper rather than a filter copied into nine
routes. Out-of-scope rows answer `404`, not `403`: "you may not see this" still
confirms it exists.

Fourteen tests take every route from the wrong side — survey list, cross-survey sign
list, review queue, features, export, crops, delete, labelling, account
administration. A tenancy bug does not show up in normal use; it shows up as one city
reading another city's survey.

## Known gaps

- **Everyone inside an organisation sees all of its surveys.** There is no per-user
  or per-project restriction within a tenant.
- **`secure` is not set on the session cookie by default**, so it works on
  `localhost`. Set it when terminating TLS.
- **Basemap URLs are stored per organisation** because a tile URL can carry an access
  key in its path — but they are readable by every member of that organisation.
