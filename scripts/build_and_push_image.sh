#!/usr/bin/env bash
set -euo pipefail

# Simple helper to build and push the backend image to Docker Hub.
# Works on macOS (zsh) and Linux. Supports buildx for multi-arch builds.

IMAGE_NS=${IMAGE_NS:-your-dockerhub-username}
IMAGE_NAME=${IMAGE_NAME:-transcript-app}
IMAGE_TAG=${IMAGE_TAG:-latest}
DOCKERFILE=${DOCKERFILE:-docker/Dockerfile.backend}
CONTEXT_DIR=${CONTEXT_DIR:-.}

# Optional: set BUILD_PLATFORMS to something like "linux/amd64" or "linux/amd64,linux/arm64"
BUILD_PLATFORMS=${BUILD_PLATFORMS:-}
# If DRY_RUN=1, we will build but not push. For multi-arch, we'll pick the first platform.
DRY_RUN=${DRY_RUN:-0}
# Optional builder name (for buildx multi-arch); default to transcript-builder
BUILDER_NAME=${BUILDER_NAME:-transcript-builder}

IMAGE_REF="${IMAGE_NS}/${IMAGE_NAME}:${IMAGE_TAG}"

echo "Image: ${IMAGE_REF}"
echo "Dockerfile: ${DOCKERFILE}"
echo "Context: ${CONTEXT_DIR}"

if [[ -n "${BUILD_PLATFORMS}" ]]; then
	echo "Using buildx for multi-arch build: ${BUILD_PLATFORMS}"
	# Ensure buildx is available and a builder is set
	if ! docker buildx ls >/dev/null 2>&1; then
		echo "docker buildx not available; please install/update Docker Desktop or Docker CLI with buildx support." >&2
		exit 1
	fi
	# Ensure a docker-container driver builder exists (default driver may be 'docker', which doesn't support multi-arch)
	CURRENT_DRIVER=$(docker buildx inspect 2>/dev/null | awk -F': ' '/Driver: /{print $2}' || true)
	if [[ "${CURRENT_DRIVER}" != "docker-container" ]]; then
		echo "Creating/using buildx builder '${BUILDER_NAME}' with docker-container driver"
		if ! docker buildx inspect "${BUILDER_NAME}" >/dev/null 2>&1; then
			docker buildx create --name "${BUILDER_NAME}" --driver docker-container --use --bootstrap
		else
			docker buildx use "${BUILDER_NAME}"
			docker buildx inspect "${BUILDER_NAME}" >/dev/null || docker buildx create --name "${BUILDER_NAME}" --driver docker-container --use --bootstrap
		fi
	else
		echo "Using existing buildx builder with driver: ${CURRENT_DRIVER}"
	fi
	if [[ "${DRY_RUN}" == "1" ]]; then
		# --load supports a single platform; pick the first if a comma-separated list was provided
		FIRST_PLATFORM=${BUILD_PLATFORMS%%,*}
		echo "DRY_RUN=1 → building only (no push), platform: ${FIRST_PLATFORM}"
		docker buildx build \
			--platform "${FIRST_PLATFORM}" \
			-t "${IMAGE_REF}" \
			-f "${DOCKERFILE}" \
			"${CONTEXT_DIR}" \
			--load
	else
			docker buildx build \
			--platform "${BUILD_PLATFORMS}" \
			-t "${IMAGE_REF}" \
			-f "${DOCKERFILE}" \
			"${CONTEXT_DIR}" \
			--push
	fi
else
	echo "Building local-arch image (no explicit platform)"
	docker build -t "${IMAGE_REF}" -f "${DOCKERFILE}" "${CONTEXT_DIR}"
	if [[ "${DRY_RUN}" == "1" ]]; then
		echo "DRY_RUN=1 → skipping push"
	else
		echo "Pushing ${IMAGE_REF}"
		docker push "${IMAGE_REF}"
	fi
fi

echo "Done: ${IMAGE_REF}"
