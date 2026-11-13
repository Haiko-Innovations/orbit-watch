import type { Abi } from "viem";
import eas from "../../../core/src/orbit_watch/chain/abi/IEAS.json";
import token from "../../../core/src/orbit_watch/chain/abi/IERC20Metadata.json";
import escrow from "../../../core/src/orbit_watch/chain/abi/OrbitWatchEscrow.json";

// The contracts' interfaces, from the same files the Python service uses, which a test keeps
// equal to the Foundry build (core/tests/test_evm_adapter.py). The browser reads with them what a
// prepared transaction does, instead of taking the service's word for it (decision P3-06).

export const escrowAbi = escrow as Abi;
export const tokenAbi = token as Abi;
export const easAbi = eas as Abi;
