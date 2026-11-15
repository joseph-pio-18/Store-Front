function isProduct(value) {
  if (!value || typeof value !== 'object') return false
  const product = value
  return (
    typeof product.item_code === 'string' &&
    typeof product.item_name === 'string' &&
    typeof product.selling_price === 'number' &&
    typeof product.stock_uom === 'string' &&
    (product.product_category === null || typeof product.product_category === 'string') &&
    (product.website_image === null || typeof product.website_image === 'string') &&
    (product.website_description === null || typeof product.website_description === 'string') &&
    (product.currency === null || typeof product.currency === 'string') &&
    Array.isArray(product.colors) &&
    product.colors.every(
      (color) =>
        color &&
        typeof color.color === 'string' &&
        (color.image === null || typeof color.image === 'string'),
    ) &&
    Array.isArray(product.variants) &&
    product.variants.every(
      (variant) =>
        variant &&
        typeof variant.variant_id === 'string' &&
        typeof variant.color === 'string' &&
        typeof variant.size === 'string' &&
        Number.isInteger(variant.available_qty) &&
        variant.available_qty >= 0,
    )
  )
}

function isProductArray(value) {
  return Array.isArray(value) && value.every(isProduct)
}

function isCustomerBag(value) {
  return (
    Array.isArray(value) &&
    value.every(
      (row) =>
        row &&
        typeof row.product_id === 'string' &&
        (row.variant_id === null || typeof row.variant_id === 'string') &&
        (row.color === null || typeof row.color === 'string') &&
        (row.size === null || typeof row.size === 'string') &&
        Number.isInteger(row.qty) &&
        row.qty >= 1 &&
        row.qty <= 99 &&
        (row.product === null || isProduct(row.product)),
    )
  )
}

class FrappeApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

export async function getProducts(search, signal, category) {
  const params = new URLSearchParams({ limit: '50', start: '0' })
  if (search.trim()) params.set('search', search.trim())
  if (category && category !== 'All products') params.set('category', category)

  const response = await fetch(`/api/method/textile_erp.api.get_products?${params}`, { signal })
  if (!response.ok) {
    throw new Error(`Catalog request failed (${response.status}).`)
  }

  const body = await response.json()
  if (!isProductArray(body.message)) {
    throw new Error('The catalog API returned an unexpected response.')
  }
  return body.message
}

async function getCsrfToken() {
  const response = await fetch('/api/method/textile_erp.api.get_csrf_token', {
    credentials: 'same-origin',
  })
  if (!response.ok) {
    throw new Error('Could not establish a secure session. Refresh the page and try again.')
  }
  const body = await response.json()
  if (typeof body.message !== 'string' || !body.message) {
    throw new Error('The server did not provide a CSRF token.')
  }
  return body.message
}

async function postForm(path, values) {
  const csrfToken = await getCsrfToken()
  const body = new URLSearchParams(values)
  const response = await fetch(path, {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
      'X-Frappe-CSRF-Token': csrfToken,
    },
    body,
  })
  const result = await response.json()
  if (!response.ok) {
    throw new FrappeApiError(getFrappeErrorMessage(result, response.status), response.status)
  }
  return result
}

function getFrappeErrorMessage(result, status) {
  if (Array.isArray(result?._server_messages)) {
    for (const rawMessage of [...result._server_messages].reverse()) {
      try {
        const parsed = JSON.parse(rawMessage)
        const message = parsed.message || parsed
        const text = document.createElement('div')
        text.innerHTML = String(message)
        if (text.textContent.trim()) return text.textContent.trim()
      } catch {
        continue
      }
    }
  }
  return `Request failed (${status}). Please try again.`
}

export async function getLoggedInUser() {
  const response = await fetch('/api/method/textile_erp.api.get_customer_session', {
    credentials: 'same-origin',
  })
  if (!response.ok) {
    throw new Error('Could not check the current sign-in session.')
  }
  const result = await response.json()
  if (!result.message) return null
  if (typeof result.message.email !== 'string') {
    throw new Error('The signed-in account response was invalid.')
  }
  return result.message
}

export async function login(email, password) {
  try {
    await postForm('/api/method/login', { usr: email.trim().toLowerCase(), pwd: password })
    const user = await getLoggedInUser()
    if (!user) throw new Error('Sign-in did not create an authenticated session.')
    return user
  } catch (error) {
    if (error instanceof FrappeApiError && [401, 403].includes(error.status)) {
      throw new Error('Email or password is incorrect, or the account is not active.')
    }
    throw error
  }
}

export async function startCustomerRegistration({ email, fullName }) {
  const result = await postForm('/api/method/textile_erp.api.start_customer_registration', {
    email: email.trim().toLowerCase(),
    full_name: fullName.trim(),
  })
  if (!result.message || typeof result.message.account_exists !== 'boolean') {
    throw new Error('The registration response was invalid.')
  }
  return result.message
}

export async function verifyCustomerRegistration({ email, otp, fullName, password, confirmPassword }) {
  return postForm('/api/method/textile_erp.api.verify_customer_registration', {
    email: email.trim().toLowerCase(),
    otp,
    full_name: fullName.trim(),
    password,
    confirm_password: confirmPassword,
  })
}

export async function logout() {
  await postForm('/api/method/logout', {})
}

export async function getCustomerBag() {
  const response = await fetch('/api/method/textile_erp.api.get_customer_bag', {
    credentials: 'same-origin',
  })
  const result = await response.json()
  if (!response.ok) {
    throw new FrappeApiError(getFrappeErrorMessage(result, response.status), response.status)
  }
  if (!isCustomerBag(result.message)) {
    throw new Error('The saved shopping bag response was invalid.')
  }
  return result.message
}

export async function updateCustomerBag(items) {
  const result = await postForm('/api/method/textile_erp.api.update_customer_bag', {
    items: JSON.stringify(items),
  })
  if (!isCustomerBag(result.message)) {
    throw new Error('The server returned an invalid saved shopping bag.')
  }
  return result.message
}

export async function placeStoreOrder() {
  const result = await postForm('/api/method/textile_erp.api.place_store_order', {})
  if (
    !result.message ||
    typeof result.message.order_id !== 'string' ||
    typeof result.message.total_amount !== 'number' ||
    typeof result.message.expected_delivery_date !== 'string'
  ) {
    throw new Error('The server returned an invalid order confirmation.')
  }
  return result.message
}
